"""Evidence fusion (Phase 4R repair).

Takes the REAL ranked candidates from the upstream pipeline and organises their evidence into separate, traceable groups:
phenotype evidence, retrieval evidence, disease-phenotype association, genetic evidence, population-frequency evidence, and
contradictory / unverified evidence. It does not recompute or alter retrieval, phenotype, population or final scores, does not
add scores from different scales, and does not treat correlated sources as independent proof. Labels are descriptive rules
(see labels.py), not calibrated confidences. Legacy keys used by the UI / tests are kept.
"""
from typing import Any, Dict, List, Optional

from src.reasoning.evidence_builder import EvidenceBuilder
from src.reasoning.labels import LABEL_RULES

_CATEGORY = {
    "phenotype_match": "SUPPORTING", "gene_association": "SUPPORTING",
    "contradiction": "CONTRADICTING",
    "patient_phenotype_not_annotated": "MISSING", "disease_phenotype_unverified": "MISSING", "disease_phenotypes_unavailable": "MISSING",
    "gene_association_unavailable": "MISSING", "variant_evidence_unavailable": "MISSING", "population_unavailable": "MISSING",
    "retrieval": "NEUTRAL", "population_evidence": "NEUTRAL", "score_breakdown": "NEUTRAL",   # frequency / similarity are not support
}
_ASPECT = {
    "phenotype_match": "Phenotype Match", "patient_phenotype_not_annotated": "Phenotype Match", "disease_phenotype_unverified": "Phenotype Match",
    "disease_phenotypes_unavailable": "Phenotype Match", "retrieval": "Semantic Knowledge Retrieval", "gene_association": "Associated Genetics",
    "gene_association_unavailable": "Associated Genetics", "variant_evidence_unavailable": "Associated Genetics",
    "population_evidence": "Population Frequency Evidence", "population_unavailable": "Population Frequency Evidence",
    "contradiction": "Contradictory Evidence", "score_breakdown": "Score Breakdown",
}


class EvidenceFusionEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None, disease_records: Optional[Dict[str, Dict[str, Any]]] = None,
                 weights: Optional[Dict[str, float]] = None):
        self.config = config or {}
        self.builder = EvidenceBuilder(disease_records or {}, weights or {})

    def set_context(self, disease_records: Dict[str, Dict[str, Any]], weights: Dict[str, float]):
        self.builder.disease_records = disease_records
        self.builder.weights = weights

    def fuse_candidate_evidence(self, candidate: Dict[str, Any], extracted_phenotypes: List[Dict[str, Any]], hpo_terms: List[Dict[str, Any]],
                                rank: int, clinical_text: str = "", retrieval_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pk = self.builder.build(candidate, rank, hpo_terms, extracted_phenotypes, clinical_text, retrieval_metadata)
        pop = candidate.get("population") or {}
        pop_status = candidate.get("population_evidence_status", pop.get("status", "unavailable"))
        ph, rt = candidate.get("phenotype_score"), candidate.get("retrieval_score")
        lbl = pk["labels"]
        unverified = [i for i in pk["evidence"] if i["type"] == "disease_phenotype_unverified"]
        items = [{"id": i["id"], "category": _CATEGORY.get(i["type"], "NEUTRAL"), "aspect": _ASPECT.get(i["type"], i["type"]),
                  "description": i["text"], "source": i["source"], "type": i["type"], "confidence": "", "score": None}
                 for i in pk["evidence"]]
        return {
            "disease_id": candidate.get("disease_id"), "disease_name": candidate.get("disease_name"), "rank": rank,
            "baseline_rank": candidate.get("baseline_rank"), "rank_change": candidate.get("rank_change"),
            "final_score": candidate.get("final_score"), "base_score": candidate.get("base_score"),
            "phenotype_score": ph, "retrieval_score": rt, "population": pop,
            "population_contribution": candidate.get("population_contribution"),
            "phenotype_evidence": {"score": ph, "confidence": lbl["label"], "label": lbl["label"], "labels": lbl["labels"],
                                   "matched_fraction": lbl["matched_fraction"],
                                   "matched_hpo_ids": [m["hpo_id"] for m in pk["matched_phenotypes"]], "matched_phenotypes": pk["matched_phenotypes"],
                                   "missing_phenotypes": [n for i in unverified for n in i["data"].get("names", [])],
                                   "unverified_note": "Annotated to the disease but not stated in the patient record; absence is not established.",
                                   "contradicting_phenotypes": pk["negated_mentions"]},
            "retrieval_evidence": {"score": rt, "confidence": "retrieval score (not a probability)", "label": "retrieval score (not a probability)",
                                   "sources": [candidate.get("source_db")] if candidate.get("source_db") else []},
            "population_evidence": {"indian_signal": candidate.get("indian_population_signal"), "global_signal": candidate.get("global_population_signal"),
                                    "status": pop_status, "confidence": "", "label": "population frequency is not disease probability",
                                    "category": "NEUTRAL" if pop_status == "available" else "MISSING"},
            "genes": pk["genes"], "evidence_items": items, "evidence_sources": sorted({i["source"] for i in pk["evidence"]}),
            "packet": pk, "labels": lbl, "evidence_completeness": pk["completeness"], "score_breakdown": pk["score_breakdown"],
            "label_rules": LABEL_RULES,
        }

    def fuse_all_candidates(self, ranked_candidates: List[Dict[str, Any]], extracted_phenotypes: List[Dict[str, Any]],
                            hpo_terms: List[Dict[str, Any]], top_k: int = 5, clinical_text: str = "",
                            retrieval_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return [self.fuse_candidate_evidence(c, extracted_phenotypes, hpo_terms, i, clinical_text, retrieval_metadata)
                for i, c in enumerate(ranked_candidates[:top_k], 1)]
