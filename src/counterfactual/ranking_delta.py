from typing import List, Dict, Any
from src.counterfactual.schemas import CandidateRankDelta

def compute_ranking_deltas(
    baseline_ranked: List[Dict[str, Any]],
    counterfactual_ranked: List[Dict[str, Any]]
) -> List[CandidateRankDelta]:
    """
    Computes exact rank shifts, score deltas, and movement trends between
    original baseline candidates and modified counterfactual candidates.
    """
    # Create lookup map for counterfactual results
    cf_map = {}
    for cand in counterfactual_ranked:
        did = cand.get("disease_id") or cand.get("disease_name")
        cf_map[did] = cand

    deltas: List[CandidateRankDelta] = []
    base_ids = {(c.get("disease_id") or c.get("disease_name")) for c in baseline_ranked}

    for b_cand in baseline_ranked:
        did = b_cand.get("disease_id") or b_cand.get("disease_name")
        dname = b_cand.get("disease_name", "Unknown Disease")
        orig_rank = b_cand.get("rank", 1)
        orig_score = float(b_cand.get("final_score", 0.0))

        cf_cand = cf_map.get(did)
        if cf_cand:
            cf_rank = cf_cand.get("rank", orig_rank)
            cf_score = float(cf_cand.get("final_score", orig_score))
            score_delta = round(cf_score - orig_score, 4)
            rank_change = orig_rank - cf_rank  # Positive if moved up to better rank
        else:  # absent from the scenario list: no rank or score is invented
            cf_rank, cf_score, score_delta, rank_change = None, None, None, None

        if rank_change is None:
            trend = "left_list"
        elif rank_change > 0:
            trend = "up"
        elif rank_change < 0:
            trend = "down"
        else:
            trend = "unchanged"

        deltas.append(CandidateRankDelta(
            disease_id=did,
            disease_name=dname,
            original_rank=orig_rank,
            counterfactual_rank=cf_rank,
            original_score=orig_score,
            counterfactual_score=cf_score,
            score_delta=score_delta,
            rank_change=rank_change,
            trend=trend
        ))

    for c in counterfactual_ranked:  # candidates that only exist in the scenario list
        did = c.get("disease_id") or c.get("disease_name")
        if did not in base_ids:
            deltas.append(CandidateRankDelta(disease_id=did, disease_name=c.get("disease_name", "Unknown Disease"),
                                             counterfactual_rank=c.get("rank"), counterfactual_score=float(c.get("final_score", 0.0)),
                                             trend="entered_list"))

    return deltas
