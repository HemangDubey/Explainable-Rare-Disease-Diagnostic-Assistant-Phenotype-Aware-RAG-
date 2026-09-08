import os
import sys
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.reasoning.llm_provider import get_llm_provider, BaseLLMProvider

logger = logging.getLogger(__name__)

class CandidateRef(BaseModel):
    disease_id: str
    disease_name: str
    rank: int

class PhenotypeReasoning(BaseModel):
    supporting: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    contradicting: List[str] = Field(default_factory=list)

class CandidateExplanationSchema(BaseModel):
    candidate: CandidateRef
    reasoning_summary: str
    phenotype_reasoning: PhenotypeReasoning
    retrieval_reasoning: str
    population_reasoning: str
    gene_reasoning: str
    overall_assessment: str
    limitations: List[str]
    evidence_references: List[str]

CLINICAL_SYSTEM_PROMPT = """You are an Explainable Rare-Disease Clinical Diagnostic Reasoning Assistant.
Your objective is to provide a strictly evidence-grounded clinical explanation for why a specific candidate disease was prioritized by the diagnostic pipeline.

CRITICAL RULES:
1. USE ONLY THE SUPPLIED EVIDENCE. Do NOT invent facts, genes, phenotypes, allele frequencies, clinical history, or citations.
2. If any piece of evidence is missing or unavailable, explicitly state "Evidence unavailable" or "No matching population record was found".
3. NEVER describe any candidate as a "Confirmed Diagnosis". Refer to it strictly as "Prioritized Candidate".
4. Do NOT make unsupported therapeutic, drug, or treatment claims. State that clinical & molecular confirmation is required.
5. You MUST return valid JSON adhering strictly to the requested schema.
"""

class LLMReasoner:
    """
    LLM Reasoner Engine (Phase 4).
    Produces structured, validated, evidence-grounded clinical explanations.
    Features local deterministic caching based on SHA256 hashes of input evidence.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider: BaseLLMProvider = get_llm_provider(config)
        self.cache: Dict[str, Dict[str, Any]] = {}

    def _compute_hash(self, candidate_evidence: Dict[str, Any]) -> str:
        content_str = json.dumps(candidate_evidence, sort_keys=True)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    def explain_candidate(
        self,
        candidate_evidence: Dict[str, Any],
        clinical_case_text: str
    ) -> Dict[str, Any]:
        """
        Generates structured LLM explanation for a single prioritized candidate disease.
        """
        cache_key = self._compute_hash(candidate_evidence)
        if cache_key in self.cache:
            logger.info("Using cached LLM explanation.")
            return self.cache[cache_key]

        disease_name = candidate_evidence.get("disease_name", "Unknown Disease")
        disease_id = candidate_evidence.get("disease_id", "Unknown")
        rank = candidate_evidence.get("rank", 1)

        user_prompt = f"""Explain why the following disease candidate was prioritized for this clinical case.

=== CLINICAL CASE ===
{clinical_case_text}

=== CANDIDATE EVIDENCE DATA ===
Candidate: {disease_name} ({disease_id}), Rank: {rank}
Final Priority Score: {candidate_evidence.get('final_score')}
Phenotype Score: {candidate_evidence.get('phenotype_evidence', {}).get('score')}
Phenotype Confidence: {candidate_evidence.get('phenotype_evidence', {}).get('confidence')}
Matched Phenotypes: {json.dumps(candidate_evidence.get('phenotype_evidence', {}).get('matched_phenotypes', []))}
Missing Phenotypes: {json.dumps(candidate_evidence.get('phenotype_evidence', {}).get('missing_phenotypes', []))}
Retrieval Score: {candidate_evidence.get('retrieval_evidence', {}).get('score')}
Retrieval Confidence: {candidate_evidence.get('retrieval_evidence', {}).get('confidence')}
Associated Genes: {json.dumps(candidate_evidence.get('genes', []))}
Population Evidence Status: {candidate_evidence.get('population_evidence', {}).get('status')}
Indian Population Signal: {candidate_evidence.get('population_evidence', {}).get('indian_signal')}
Global Population Signal: {candidate_evidence.get('population_evidence', {}).get('global_signal')}
Evidence Sources: {json.dumps(candidate_evidence.get('evidence_sources', []))}

=== INSTRUCTIONS ===
Generate a valid JSON object with the following exact keys:
{{
  "candidate": {{
    "disease_id": "{disease_id}",
    "disease_name": "{disease_name}",
    "rank": {rank}
  }},
  "reasoning_summary": "Concise summary explaining why this disease was prioritized based on real scores and evidence.",
  "phenotype_reasoning": {{
    "supporting": ["Matched patient phenotypes and their clinical relevance"],
    "missing": ["Expected disease phenotypes not documented in patient"],
    "contradicting": []
  }},
  "retrieval_reasoning": "Explanation of semantic knowledge-base similarity match.",
  "population_reasoning": "Explanation of Indian (IndiGen) and global (gnomAD) population signals.",
  "gene_reasoning": "Explanation of causal/associated genes identified, or state 'No associated genes found'.",
  "overall_assessment": "Balanced non-diagnostic synthesis of evidence strength and clinical implications.",
  "limitations": [
    "State that this is an evidence-supported candidate prioritization and NOT a confirmed diagnosis.",
    "State that molecular genetic testing and clinical correlation are required."
  ],
  "evidence_references": ["Traceable sources such as HPO, OMIM, IndiGen, gnomAD"]
}}
"""

        try:
            # Check Ollama health
            health = self.provider.check_health()
            if health.get("status") != "healthy":
                logger.warning(f"Ollama health check returned: {health}")
                # Fallback to rule-based structured explanation if Ollama unavailable
                fallback_explanation = self._generate_rule_based_explanation(candidate_evidence)
                return fallback_explanation

            # Query Ollama
            response_json = self.provider.generate_json(
                prompt=user_prompt,
                system_prompt=CLINICAL_SYSTEM_PROMPT
            )

            # Validate with Pydantic
            try:
                validated = CandidateExplanationSchema(**response_json).dict()
                self.cache[cache_key] = validated
                return validated
            except Exception as val_err:
                logger.warning(f"Schema validation error: {val_err}. Retrying once or repairing...")
                # Attempt safe repair
                repaired = self._repair_json_structure(response_json, candidate_evidence)
                validated = CandidateExplanationSchema(**repaired).dict()
                self.cache[cache_key] = validated
                return validated

        except Exception as e:
            logger.error(f"LLM Reasoning failed: {e}. Generating rule-based explanation.")
            return self._generate_rule_based_explanation(candidate_evidence)

    def _repair_json_structure(self, raw: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures all required fields exist."""
        d_name = evidence.get("disease_name", "Unknown Disease")
        d_id = evidence.get("disease_id", "Unknown")
        rank = evidence.get("rank", 1)

        repaired = {
            "candidate": raw.get("candidate", {
                "disease_id": d_id,
                "disease_name": d_name,
                "rank": rank
            }),
            "reasoning_summary": raw.get("reasoning_summary", f"{d_name} prioritized with composite score {evidence.get('final_score')}."),
            "phenotype_reasoning": raw.get("phenotype_reasoning", {
                "supporting": [m.get("name", "") for m in evidence.get("phenotype_evidence", {}).get("matched_phenotypes", [])],
                "missing": evidence.get("phenotype_evidence", {}).get("missing_phenotypes", []),
                "contradicting": []
            }),
            "retrieval_reasoning": raw.get("retrieval_reasoning", f"Semantic retrieval similarity score: {evidence.get('retrieval_evidence', {}).get('score')}."),
            "population_reasoning": raw.get("population_reasoning", f"Population prior status: {evidence.get('population_evidence', {}).get('status')}."),
            "gene_reasoning": raw.get("gene_reasoning", f"Associated genes: {', '.join(evidence.get('genes', [])) or 'None mapped'}."),
            "overall_assessment": raw.get("overall_assessment", "Evidence indicates moderate-to-high phenotypic alignment. Clinical correlation recommended."),
            "limitations": raw.get("limitations", [
                "Prioritized candidate decision-support only; not a definitive diagnosis.",
                "Molecular and clinical validation required."
            ]),
            "evidence_references": raw.get("evidence_references", evidence.get("evidence_sources", []))
        }
        return repaired

    def _generate_rule_based_explanation(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Safe rule-based fallback explanation when LLM is offline."""
        d_name = evidence.get("disease_name", "Unknown Disease")
        d_id = evidence.get("disease_id", "Unknown")
        rank = evidence.get("rank", 1)
        p_evidence = evidence.get("phenotype_evidence", {})
        r_evidence = evidence.get("retrieval_evidence", {})
        pop_evidence = evidence.get("population_evidence", {})
        genes = evidence.get("genes", [])

        matched_ph = [m.get("name", "") for m in p_evidence.get("matched_phenotypes", [])]

        return {
            "candidate": {
                "disease_id": d_id,
                "disease_name": d_name,
                "rank": rank
            },
            "reasoning_summary": f"Candidate {d_name} was prioritized at Rank #{rank} with a composite priority score of {evidence.get('final_score', 0.0):.4f}. It demonstrates {p_evidence.get('confidence', 'Moderate').lower()} phenotypic overlap and {r_evidence.get('confidence', 'Moderate').lower()} semantic retrieval similarity.",
            "phenotype_reasoning": {
                "supporting": [f"Matches patient phenotype: {p}" for p in matched_ph] if matched_ph else ["No direct HPO terms matched"],
                "missing": p_evidence.get("missing_phenotypes", []),
                "contradicting": []
            },
            "retrieval_reasoning": f"Knowledge base dense semantic similarity score of {r_evidence.get('score', 0.0):.4f} ({r_evidence.get('confidence', 'Moderate')} confidence).",
            "population_reasoning": f"Population prior status is '{pop_evidence.get('status', 'unavailable')}' (Indian signal: {pop_evidence.get('indian_signal', 0.5):.4f}, Global signal: {pop_evidence.get('global_signal', 0.5):.4f}).",
            "gene_reasoning": f"Associated causal genes: {', '.join(genes)}" if genes else "No causal genes mapped in current record.",
            "overall_assessment": "The candidate shows clinical alignment with patient findings. This represents a prioritized decision-support candidate requiring specialist evaluation.",
            "limitations": [
                "Decision-support output only; does not establish a confirmed diagnosis.",
                "Requires confirmatory molecular genetic testing and clinical specialist evaluation."
            ],
            "evidence_references": evidence.get("evidence_sources", ["HPO", "OMIM", "IndiGen", "gnomAD"])
        }
