from typing import List, Dict, Any
from src.counterfactual.schemas import CandidateRankDelta, PhenotypeImpactItem

def generate_counterfactual_insights(
    operation: str,
    target_phenotype: str,
    deltas: List[CandidateRankDelta],
    impacts: List[PhenotypeImpactItem]
) -> List[str]:
    """
    Generates grounded, non-causal analytical insights based strictly on computed
    rank changes, score deltas, and sensitivity impact scores.
    """
    insights: List[str] = []

    if not deltas:
        insights.append("No diagnostic candidates were retrieved for the counterfactual configuration.")
        return insights

    top_delta = deltas[0]
    op_label = operation.lower()

    if op_label == "remove" and target_phenotype:
        if top_delta.rank_change != 0:
            direction_str = f"moved from rank #{top_delta.original_rank} to #{top_delta.counterfactual_rank}"
        else:
            direction_str = f"remained at rank #{top_delta.original_rank}"
        
        insights.append(
            f"Removing phenotype '{target_phenotype}' changed candidate '{top_delta.disease_name}' score by {top_delta.score_delta:+.4f} and {direction_str}."
        )
    elif op_label == "add" and target_phenotype:
        insights.append(
            f"Adding phenotype '{target_phenotype}' shifted top candidate '{top_delta.disease_name}' score by {top_delta.score_delta:+.4f} (new rank: #{top_delta.counterfactual_rank})."
        )
    elif op_label == "toggle" and target_phenotype:
        insights.append(
            f"Toggling phenotype '{target_phenotype}' resulted in a score delta of {top_delta.score_delta:+.4f} for '{top_delta.disease_name}'."
        )
    else:
        insights.append(
            f"Counterfactual case state comparison revealed a peak score shift of {top_delta.score_delta:+.4f} for top candidate '{top_delta.disease_name}'."
        )

    # Highlight candidate with largest rank movement
    rank_movers = [d for d in deltas if abs(d.rank_change) > 0]
    if rank_movers:
        most_moved = max(rank_movers, key=lambda x: abs(x.rank_change))
        insights.append(
            f"Candidate '{most_moved.disease_name}' experienced the largest rank movement ({'↑' if most_moved.rank_change > 0 else '↓'}{abs(most_moved.rank_change)} positions)."
        )

    # Highest sensitivity phenotype insight
    if impacts:
        top_impact = impacts[0]
        insights.append(
            f"Phenotype '{top_impact.hpo_name}' ({top_impact.hpo_id}) exhibited the highest ranking sensitivity with a score impact delta of {top_impact.impact_score:.4f}."
        )

    insights.append(
        "Note: This is a computational sensitivity analysis evaluating algorithmic prior shifts and does not establish clinical causality."
    )

    return insights
