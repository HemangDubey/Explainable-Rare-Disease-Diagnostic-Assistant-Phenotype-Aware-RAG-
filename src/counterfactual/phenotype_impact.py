from typing import List, Dict, Any
from src.counterfactual.schemas import PhenotypeImpactItem

def calculate_phenotype_impacts(
    baseline_hpos: List[Dict[str, Any]],
    baseline_ranked: List[Dict[str, Any]],
    ranking_pipeline_fn
) -> List[PhenotypeImpactItem]:
    """
    Calculates phenotype influence / score sensitivity across candidate diseases.
    Formula: phenotype_impact = baseline_score - ablated_score (case without phenotype).
    Categorizes into High, Moderate, or Low ranking sensitivity.
    """
    impact_items: List[PhenotypeImpactItem] = []
    if not baseline_hpos or not baseline_ranked:
        return impact_items

    baseline_top_score = float(baseline_ranked[0].get("final_score", 0.0))
    all_hpo_terms = [h.get("name", h.get("hpo_id")) for h in baseline_hpos]

    for h_obj in baseline_hpos:
        hid = h_obj.get("hpo_id", "")
        hname = h_obj.get("name", hid)

        # Single phenotype ablation: run ranking pipeline on phenotype set excluding this phenotype
        ablated_terms = [h for h in baseline_hpos if h.get("hpo_id") != hid]

        if not ablated_terms:
            impact_score = baseline_top_score
        else:
            p3_ablated = ranking_pipeline_fn(ablated_terms, top_k_disease=len(baseline_ranked))
            ablated_candidates = p3_ablated.get("ranked_candidates", [])
            
            if ablated_candidates:
                ablated_top_score = float(ablated_candidates[0].get("final_score", 0.0))
                impact_score = round(abs(baseline_top_score - ablated_top_score), 4)
            else:
                impact_score = round(baseline_top_score, 4)

        # Classify sensitivity level based on actual calculated score delta
        if impact_score >= 0.12:
            sensitivity = "High ranking sensitivity"
        elif impact_score >= 0.04:
            sensitivity = "Moderate ranking sensitivity"
        else:
            sensitivity = "Low ranking sensitivity"

        impact_items.append(PhenotypeImpactItem(
            hpo_id=hid,
            hpo_name=hname,
            impact_score=float(impact_score),
            sensitivity_level=sensitivity,
            affected_candidates_count=len(baseline_ranked)
        ))

    # Sort phenotypes by impact score descending
    impact_items.sort(key=lambda x: x.impact_score, reverse=True)
    return impact_items
