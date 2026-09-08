import os
import sys
import json
from typing import List, Dict, Any, Optional

class DifferentialEngine:
    """
    Differential Diagnosis Engine (Phase 4).
    Compares prioritized candidate diseases side-by-side.
    Identifies distinguishing phenotypes, score breakdowns, and comparative clinical rationales.
    Never refers to any candidate as a confirmed diagnosis.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def generate_differential(
        self,
        fused_candidates: List[Dict[str, Any]],
        clinical_case_text: str = ""
    ) -> Dict[str, Any]:
        """
        Generates comparative differential analysis across top candidates.
        """
        if not fused_candidates:
            return {
                "top_candidates": [],
                "comparisons": [],
                "distinguishing_features": [],
                "summary": "No candidate diseases available for differential analysis."
            }

        top_candidates = []
        for cand in fused_candidates:
            top_candidates.append({
                "rank": cand.get("rank"),
                "disease_id": cand.get("disease_id"),
                "disease_name": cand.get("disease_name"),
                "final_score": cand.get("final_score"),
                "phenotype_score": cand.get("phenotype_evidence", {}).get("score"),
                "retrieval_score": cand.get("retrieval_evidence", {}).get("score"),
                "indian_population_signal": cand.get("population_evidence", {}).get("indian_signal"),
                "global_population_signal": cand.get("population_evidence", {}).get("global_signal"),
                "population_status": cand.get("population_evidence", {}).get("status"),
                "matched_phenotypes": [m.get("name") for m in cand.get("phenotype_evidence", {}).get("matched_phenotypes", [])],
                "missing_phenotypes": cand.get("phenotype_evidence", {}).get("missing_phenotypes", []),
                "associated_genes": cand.get("genes", [])
            })

        # Pairwise / comparative insights against Rank #1
        primary = top_candidates[0]
        comparisons = []
        for idx in range(1, len(top_candidates)):
            cand = top_candidates[idx]
            diff_score = primary["final_score"] - cand["final_score"]
            
            # Phenotype differences
            primary_phenos = set(primary["matched_phenotypes"])
            cand_phenos = set(cand["matched_phenotypes"])
            
            shared = list(primary_phenos.intersection(cand_phenos))
            primary_unique = list(primary_phenos - cand_phenos)
            cand_unique = list(cand_phenos - primary_phenos)

            # Why Rank 1 is prioritized over this candidate:
            reasons = []
            if primary["phenotype_score"] > cand["phenotype_score"]:
                reasons.append(f"Higher phenotype alignment score ({primary['phenotype_score']:.4f} vs {cand['phenotype_score']:.4f})")
            if primary["retrieval_score"] > cand["retrieval_score"]:
                reasons.append(f"Stronger semantic retrieval similarity ({primary['retrieval_score']:.4f} vs {cand['retrieval_score']:.4f})")
            if primary["indian_population_signal"] > cand["indian_population_signal"] and primary["population_status"] == "available":
                reasons.append(f"Elevated Indian population frequency signal ({primary['indian_population_signal']:.4f} vs {cand['indian_population_signal']:.4f})")

            comparisons.append({
                "compared_rank": cand["rank"],
                "compared_disease": cand["disease_name"],
                "score_delta": round(diff_score, 4),
                "shared_phenotypes": shared,
                "primary_differentiating_phenotypes": primary_unique,
                "candidate_differentiating_phenotypes": cand_unique,
                "distinguishing_factors": reasons if reasons else ["Slight variations in multi-factor weighted composite scoring."]
            })

        # Distinguishing diagnostic phenotype checklist
        all_matched = set()
        for c in top_candidates:
            all_matched.update(c["matched_phenotypes"])

        all_missing = set()
        for c in top_candidates:
            all_missing.update(c["missing_phenotypes"])

        distinguishing_features = [
            {
                "phenotype": feat,
                "clinical_utility": "Can help discriminate between top differential candidates if confirmed in physical exam or genetics."
            }
            for feat in list(all_missing)[:5]
        ]

        summary = (
            f"The differential diagnosis is led by Rank #1 candidate '{primary['disease_name']}' "
            f"(composite score: {primary['final_score']:.4f}), which demonstrates the strongest overall combination "
            f"of phenotype congruence and knowledge retrieval. Additional candidates remain in the differential "
            f"due to overlapping clinical signs."
        )

        return {
            "top_candidates": top_candidates,
            "comparisons": comparisons,
            "distinguishing_features": distinguishing_features,
            "summary": summary,
            "disclaimer": "This differential comparison is an algorithmic decision-support aid and does not constitute a confirmed medical diagnosis. Clinical correlation and genetic confirmation are required."
        }
