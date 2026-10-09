"""Transparent, rule-based evidence labels. NOTHING here is a calibrated probability.

The previous tiers ("High/Moderate/Low confidence") were thresholds on cosine scores / overlap counts that were never
calibrated against outcomes. They are replaced by descriptive labels with the explicit rules below. These labels describe
how much evidence is *available in this system*; they do not state how likely a disease is, and absence of evidence in the
system does not establish absence of disease. `calibrated` is always False because no calibration study has been run.
"""
from typing import Dict, List, Optional

LABEL_RULES: Dict[str, str] = {
    "Strong phenotype overlap": "matched_fraction >= 0.75 (share of the patient's mapped HPO terms that are annotated to the disease)",
    "Partial phenotype overlap": "0.40 <= matched_fraction < 0.75",
    "Limited supporting evidence": "0 < matched_fraction < 0.40",
    "Insufficient evidence": "matched_fraction == 0, or the patient has no mapped HPO terms",
    "Conflicting evidence": "the patient record explicitly negates a phenotype that is annotated to the disease (shown in addition to the overlap label)",
}
COMPLETENESS_RULE = ("evidence_completeness = (number of available evidence categories) / 3 over: phenotype overlap, "
                     "disease-gene association in the knowledge base, population-frequency evidence. Literature evidence is "
                     "not assessed in this phase and is reported as such. Completeness says how much was checked, not how likely the disease is.")


def overlap_label(n_matched: int, n_patient_terms: int, has_conflict: bool = False) -> Dict[str, object]:
    frac: Optional[float] = (n_matched / n_patient_terms) if n_patient_terms else None
    if not n_patient_terms or n_matched == 0:
        label = "Insufficient evidence"
    elif frac >= 0.75:
        label = "Strong phenotype overlap"
    elif frac >= 0.40:
        label = "Partial phenotype overlap"
    else:
        label = "Limited supporting evidence"
    return {"label": label, "matched_fraction": None if frac is None else round(frac, 4), "conflicting_evidence": bool(has_conflict),
            "labels": [label] + (["Conflicting evidence"] if has_conflict else []), "calibrated": False}


def completeness(categories: Dict[str, bool]) -> Dict[str, object]:
    avail = [k for k, v in categories.items() if v]
    return {"available": avail, "unavailable": [k for k, v in categories.items() if not v],
            "fraction": round(len(avail) / len(categories), 3) if categories else None,
            "literature": "not assessed in this phase", "rule": COMPLETENESS_RULE}
