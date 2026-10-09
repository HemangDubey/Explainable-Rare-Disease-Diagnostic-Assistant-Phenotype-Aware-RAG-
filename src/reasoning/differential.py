"""Evidence-linked differential diagnosis (Phase 4R).

Built only from the fused candidates (which carry the real upstream scores and evidence packets). A candidate is never
described as confirmed or ruled out; a phenotype that is merely not stated in the patient record is "unverified", not absent
(absence requires an explicit negation in the record, reported as contradictory evidence). Score differences are the real
components of the ranking, not new numbers.
"""
from typing import Any, Dict, List, Optional

DISCLAIMER = ("This differential comparison is an algorithmic decision-support aid for research use. It does not establish or exclude any diagnosis; "
              "lower-ranked candidates are not ruled out, and absence of evidence in this system does not establish absence of disease. "
              "Qualified clinical interpretation and genetic confirmation are required.")


def _names(c: Dict[str, Any]) -> List[str]:
    return [m.get("name") or m.get("hpo_id") for m in c.get("phenotype_evidence", {}).get("matched_phenotypes", [])]


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None else round(a - b, 6)


class DifferentialEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def generate_differential(self, fused_candidates: List[Dict[str, Any]], clinical_case_text: str = "") -> Dict[str, Any]:
        if not fused_candidates:
            return {"top_candidates": [], "comparisons": [], "distinguishing_features": [],
                    "summary": "No candidate diseases available for differential analysis.", "disclaimer": DISCLAIMER}
        top = []
        for c in fused_candidates:
            pk = c.get("packet") or {}
            top.append({
                "rank": c.get("rank"), "disease_id": c.get("disease_id"), "disease_name": c.get("disease_name"), "final_score": c.get("final_score"),
                "base_score": c.get("base_score"), "phenotype_score": c.get("phenotype_score", c.get("phenotype_evidence", {}).get("score")),
                "retrieval_score": c.get("retrieval_score", c.get("retrieval_evidence", {}).get("score")),
                "population_contribution": c.get("population_contribution"), "baseline_rank": c.get("baseline_rank"), "rank_change": c.get("rank_change"),
                "indian_population_signal": c.get("population_evidence", {}).get("indian_signal"),
                "global_population_signal": c.get("population_evidence", {}).get("global_signal"),
                "population_status": c.get("population_evidence", {}).get("status"),
                "matched_phenotypes": _names(c),
                "missing_phenotypes": c.get("phenotype_evidence", {}).get("missing_phenotypes", []),     # = unverified, not absent
                "contradictory_evidence": [e["text"] for e in c.get("evidence_items", []) if e.get("type") == "contradiction"],
                "associated_genes": c.get("genes", []),
                "evidence_label": (c.get("labels") or {}).get("label"), "evidence_labels": (c.get("labels") or {}).get("labels"),
                "evidence_completeness": (c.get("evidence_completeness") or {}).get("fraction"),
                "score_breakdown": c.get("score_breakdown"),
                "source_references": [{"evidence_id": e["id"], "source": e["source"]} for e in pk.get("evidence", [])
                                      if e["type"] in ("phenotype_match", "gene_association", "contradiction")],
                "uncertainties": ["Retrieval and ranking scores are not probabilities.",
                                  "Phenotypes not stated in the record are unverified, not absent.",
                                  "Literature evidence was not assessed."]
                                 + ([] if (c.get("evidence_completeness") or {}).get("fraction") == 1.0 else
                                    ["Unavailable evidence categories: " + ", ".join((c.get("evidence_completeness") or {}).get("unavailable", []) or ["unknown"])]),
            })
        primary = top[0]
        comparisons = []
        for cand in top[1:]:
            ps, cs = set(primary["matched_phenotypes"]), set(cand["matched_phenotypes"])
            factors = []
            for key, label in (("phenotype_score", "phenotype score"), ("retrieval_score", "retrieval score"), ("base_score", "base score"),
                               ("population_contribution", "population contribution")):
                d = _delta(primary.get(key), cand.get(key))
                if d is not None and d != 0:
                    factors.append(f"{label}: rank #{primary['rank']} {primary[key]:.4f} vs rank #{cand['rank']} {cand[key]:.4f} (difference {d:+.4f})")
            comparisons.append({
                "compared_rank": cand["rank"], "compared_disease": cand["disease_name"],
                "score_delta": _delta(primary["final_score"], cand["final_score"]),
                "shared_phenotypes": sorted(ps & cs),
                "primary_differentiating_phenotypes": sorted(ps - cs), "candidate_differentiating_phenotypes": sorted(cs - ps),
                "distinguishing_factors": factors or ["No difference in the recorded score components."],
                "note": "Rank order reflects the recorded score components only; the lower-ranked candidate is not ruled out.",
            })
        names = lambda c: set(c["missing_phenotypes"])  # noqa: E731
        common_unverified = set.intersection(*[names(c) for c in top]) if top else set()
        feats = []
        for c in top:
            for p in sorted(names(c) - common_unverified)[:3]:
                feats.append({"phenotype": p, "annotated_to": c["disease_name"],
                              "note": "Annotated to this candidate but not stated in the patient record. Verifying it could help compare candidates; its absence is not established."})
        summary = (f"Rank #1 is '{primary['disease_name']}' (final score {primary['final_score']:.4f}; evidence label: {primary['evidence_label']}). "
                   f"{len(top) - 1} other candidate(s) are listed for comparison. Scores are retrieval/ranking scores, not probabilities; "
                   f"no candidate is confirmed or excluded.")
        return {"top_candidates": top, "comparisons": comparisons, "distinguishing_features": feats[:8], "summary": summary, "disclaimer": DISCLAIMER}
