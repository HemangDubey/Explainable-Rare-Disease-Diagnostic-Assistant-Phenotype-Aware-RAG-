from typing import List
from src.counterfactual.schemas import CandidateRankDelta, PhenotypeImpactItem


def _fmt(delta) -> str:
    return "n/a (absent from one list)" if delta is None else f"{delta:+.4f}"


def generate_counterfactual_insights(
    operation: str,
    target_phenotype: str,
    deltas: List[CandidateRankDelta],
    impacts: List[PhenotypeImpactItem]
) -> List[str]:
    """Insights derived strictly from computed rank/score changes. Candidates absent from a list have no invented rank or score."""
    insights: List[str] = []
    if not deltas:
        return ["No diagnostic candidates were retrieved for the counterfactual configuration."]

    top = deltas[0]
    verb = {"remove": "Removing", "add": "Adding", "toggle": "Toggling"}.get(operation.lower())
    if verb and target_phenotype:
        where = (f"moved from rank #{top.original_rank} to #{top.counterfactual_rank}" if top.rank_change
                 else f"remained at rank #{top.original_rank}" if top.rank_change == 0
                 else "is not present in one of the two lists")
        insights.append(f"Hypothetically {verb.lower()[:-3]}ing phenotype '{target_phenotype}': baseline top candidate '{top.disease_name}' "
                        f"final score changed by {_fmt(top.score_delta)} and {where}.")
    else:
        insights.append(f"Comparison of the two phenotype sets: baseline top candidate '{top.disease_name}' final score changed by {_fmt(top.score_delta)}.")

    movers = [d for d in deltas if d.rank_change]
    if movers:
        m = max(movers, key=lambda x: abs(x.rank_change))
        insights.append(f"Candidate '{m.disease_name}' showed the largest rank movement ({'up' if m.rank_change > 0 else 'down'} {abs(m.rank_change)} position(s)).")
    for d in deltas:
        if d.trend == "left_list":
            insights.append(f"'{d.disease_name}' (baseline rank #{d.original_rank}) is not in the scenario list — this is not an exclusion of the disease.")
        elif d.trend == "entered_list":
            insights.append(f"'{d.disease_name}' entered the scenario list at rank #{d.counterfactual_rank}; it has no baseline rank or score.")
    if impacts:
        t = impacts[0]
        insights.append(f"Single-phenotype ablation: '{t.hpo_name}' ({t.hpo_id}) changed the top final score most (Δ {t.impact_score:.4f}).")
    insights.append("This is a computational sensitivity analysis on hypothetical input; it does not establish clinical causality or a diagnosis.")
    return insights
