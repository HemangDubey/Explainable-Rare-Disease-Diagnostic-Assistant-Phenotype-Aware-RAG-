import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional

from src.reasoning.llm_provider import get_llm_provider, BaseLLMProvider

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_PROMPT = """You are an Explainable AI Doctor Copilot for Rare Disease Diagnostic Decision Support.
You are assisting a clinician analyzing a specific patient case.

CRITICAL OPERATIONAL RULES:
1. Ground every answer STRICTLY in the provided patient case context and candidate disease evidence.
2. DO NOT hallucinate patient symptoms, genetic findings, or literature citations.
3. NEVER make definitive diagnostic declarations ("The patient has X"). Always use "Prioritized candidate", "Phenotypic evidence suggests", or "Differential diagnosis".
4. If a question asks about missing evidence, unavailable population data, or unconfirmed tests, answer transparently stating the data is unavailable.
5. Provide clinically concise, professional, actionable responses.
"""

class DoctorCopilot:
    """
    Explainable AI Doctor Copilot (Phase 4).
    Provides context-grounded interactive Q&A regarding the current patient case.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider: BaseLLMProvider = get_llm_provider(config)

    def answer_query(
        self,
        query: str,
        case_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Answers a clinician's question about the active case.
        """
        clinical_text = case_context.get("clinical_text", "")
        extracted_phenotypes = case_context.get("extracted_phenotypes", [])
        top_candidates = case_context.get("fused_candidates", [])[:5]

        # Summarize candidate evidence for the prompt
        candidates_summary = []
        for c in top_candidates:
            matched = [m.get("name", "") for m in c.get("phenotype_evidence", {}).get("matched_phenotypes", [])]
            missing = c.get("phenotype_evidence", {}).get("missing_phenotypes", [])[:3]
            candidates_summary.append({
                "rank": c.get("rank"),
                "disease_name": c.get("disease_name"),
                "disease_id": c.get("disease_id"),
                "final_score": c.get("final_score"),
                "phenotype_score": c.get("phenotype_evidence", {}).get("score"),
                "retrieval_score": c.get("retrieval_evidence", {}).get("score"),
                "indian_signal": c.get("population_evidence", {}).get("indian_signal"),
                "population_status": c.get("population_evidence", {}).get("status"),
                "matched_phenotypes": matched,
                "missing_phenotypes": missing,
                "genes": c.get("genes", [])
            })

        prompt = f"""=== PATIENT CLINICAL CASE ===
{clinical_text}

=== EXTRACTED PHENOTYPE MENTIONS ===
{json.dumps(extracted_phenotypes)}

=== TOP PRIORITIZED CANDIDATES ===
{json.dumps(candidates_summary, indent=2)}

=== CLINICIAN'S QUESTION ===
"{query}"

=== INSTRUCTIONS ===
Answer the clinician's question strictly using the provided case evidence above.
Return a JSON object formatted as follows:
{{
  "answer": "Clear, professional, evidence-linked clinical response.",
  "referenced_candidates": ["Names of candidates referred to"],
  "evidence_points": [
    "Key supporting or distinguishing evidence facts from the case"
  ],
  "recommended_follow_up": "Suggested clinical or molecular tests (e.g. Sanger sequencing, whole exome sequencing, targeted imaging, or specific phenotype evaluation) to resolve ambiguity.",
  "confidence": "High / Moderate / Preliminary"
}}
"""

        try:
            health = self.provider.check_health()
            if health.get("status") != "healthy":
                return self._rule_based_answer(query, case_context)

            response = self.provider.generate_json(
                prompt=prompt,
                system_prompt=COPILOT_SYSTEM_PROMPT
            )

            # Ensure minimal keys
            if "answer" not in response:
                response["answer"] = str(response)

            if "evidence_points" not in response:
                response["evidence_points"] = []
            if "recommended_follow_up" not in response:
                response["recommended_follow_up"] = "Comprehensive genetic testing (WES/WGS) and clinical phenotyping."
            if "confidence" not in response:
                response["confidence"] = "Moderate"

            return response

        except Exception as e:
            logger.error(f"Doctor Copilot generation error: {e}. Using fallback.")
            return self._rule_based_answer(query, case_context)

    def _rule_based_answer(self, query: str, case_context: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based clinical responses when LLM is unavailable."""
        top_candidates = case_context.get("fused_candidates", [])
        q_lower = query.lower()

        if not top_candidates:
            return {
                "answer": "No patient case has been analyzed yet. Please enter a clinical observation to prioritize candidates.",
                "referenced_candidates": [],
                "evidence_points": ["Awaiting case input"],
                "recommended_follow_up": "Analyze case text first.",
                "confidence": "Preliminary"
            }

        top1 = top_candidates[0]
        name1 = top1.get("disease_name", "Primary candidate")
        matched1 = [m.get("name", "") for m in top1.get("phenotype_evidence", {}).get("matched_phenotypes", [])]

        if "why" in q_lower or "ranked first" in q_lower or "prioritized" in q_lower:
            ans = (
                f"{name1} was prioritized first (Rank #1, final score: {top1.get('final_score'):.4f}) "
                f"because it achieved the highest composite match across phenotypic overlap "
                f"(score: {top1.get('phenotype_evidence', {}).get('score'):.4f}) and semantic retrieval similarity "
                f"(score: {top1.get('retrieval_evidence', {}).get('score'):.4f}). It matched patient phenotypes: "
                f"{', '.join(matched1)}."
            )
            ev = [f"Phenotypic overlap with {len(matched1)} features", f"Semantic retrieval score {top1.get('retrieval_evidence', {}).get('score')}"]
        elif "phenotype" in q_lower:
            ans = f"The candidate {name1} directly aligns with patient features: {', '.join(matched1)}."
            ev = matched1
        elif "population" in q_lower or "indian" in q_lower:
            pop_status = top1.get("population_evidence", {}).get("status", "unavailable")
            ans = (
                f"Indian population prior status for {name1} is '{pop_status}' with an IndiGen signal of "
                f"{top1.get('population_evidence', {}).get('indian_signal', 0.5):.4f}. "
                f"Ancestral frequency serves as an epidemiological baseline rather than diagnostic proof."
            )
            ev = [f"Population status: {pop_status}", f"IndiGen signal: {top1.get('population_evidence', {}).get('indian_signal')}"]
        else:
            ans = (
                f"Regarding your query on this case: The leading candidate is {name1} with {len(matched1)} "
                f"matching phenotypes. Additional specialist evaluation and targeted molecular sequencing are indicated."
            )
            ev = [f"Leading candidate: {name1}", f"Matches: {', '.join(matched1)}"]

        return {
            "answer": ans,
            "referenced_candidates": [name1],
            "evidence_points": ev,
            "recommended_follow_up": "Targeted gene panel, chromosomal microarray, or whole exome sequencing.",
            "confidence": "Moderate"
        }
