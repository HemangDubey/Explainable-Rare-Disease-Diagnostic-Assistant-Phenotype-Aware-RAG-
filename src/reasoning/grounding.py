"""Schema + grounding validation of model-produced explanations.

A claim survives only if (a) it cites at least one evidence id that exists for THAT candidate, (b) every decimal number /
percentage in it appears in the cited evidence, (c) every gene-like symbol in it appears in the cited evidence (or is a known
generic term), and (d) it contains no citation-like strings (PMID / DOI / URL), no definitive-diagnosis wording and no
treatment / dosage wording. Anything else is removed and counted, never silently shown.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, ValidationError

_ID = re.compile(r"\bC\d+-E\d+\b")


def extract_ids(text: str) -> List[str]:
    """Evidence ids cited inline in the text, e.g. '(C1-E2)'. Order-preserving, de-duplicated."""
    return list(dict.fromkeys(_ID.findall(text or "")))


class Claim(BaseModel):
    text: str
    evidence_ids: List[str] = Field(default_factory=list)


def _coerce_claim(v):
    """Accept a plain string (ids cited inline) or an object {text, evidence_ids}. Missing ids are taken from the text."""
    if isinstance(v, str):
        return {"text": v, "evidence_ids": extract_ids(v)}
    if isinstance(v, dict):
        ids = v.get("evidence_ids") or extract_ids(str(v.get("text", "")))
        return {"text": v.get("text", ""), "evidence_ids": [str(i) for i in ids]}
    return v


CoercedClaim = Annotated[Claim, BeforeValidator(_coerce_claim)]


class CandidateReasoning(BaseModel):
    candidate_id: str
    summary: str
    summary_evidence_ids: List[str] = Field(default_factory=list)
    ranking_note: Optional[CoercedClaim] = None
    supporting_evidence: List[CoercedClaim] = Field(default_factory=list)
    missing_or_unverified_evidence: List[CoercedClaim] = Field(default_factory=list)
    contradictory_evidence: List[CoercedClaim] = Field(default_factory=list)
    genetic_evidence: List[CoercedClaim] = Field(default_factory=list)
    population_evidence: List[CoercedClaim] = Field(default_factory=list)
    uncertainties: List[CoercedClaim] = Field(default_factory=list)


class ReasoningBatch(BaseModel):
    candidates: List[CandidateReasoning]


CLAIM_FIELDS = ["supporting_evidence", "missing_or_unverified_evidence", "contradictory_evidence", "genetic_evidence",
                "population_evidence", "uncertainties"]

_CITATION = re.compile(r"\bPMID\b|\bdoi\b|https?://|www\.|\bet al\b|\bPubMed\b", re.IGNORECASE)
_DIAGNOSIS = re.compile(r"\bpatient has\b|\b(is|are|was) (diagnosed|confirmed)\b|\bdiagnosed with\b|\bconfirms? (the )?diagnosis\b|\bdefinitive(ly)? (diagnos|establish)", re.IGNORECASE)
_TREATMENT = re.compile(r"\btreat(ment|ed|ing)?\b|\bprescrib\w*|\bdos(e|age)\b|\b\d+\s?(mg|mcg|ml)\b|\btherapy\b|\bmedicat\w*", re.IGNORECASE)
_QUALIFIER = re.compile(r"\b(high|higher|highest|strong|stronger|strongest|low|lower|lowest|weak|excellent|good|poor)\b[\w\s-]{0,22}\b(score|similarity)\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![\w.])\d+\.\d+(?:[eE][-+]?\d+)?(?![\w.])|\d+(?:\.\d+)?\s?%")
_ADVICE = re.compile(r"\b(?:is|are|be|was|were)\s+(?:indicated|recommended|advised|warranted)\b|\brecommend\w*|\badvis(?:e|ed|able)\b|\bshould\s+(?:be\s+)?(?:perform|order|undergo|test|sequenc|refer|start)\w*|"
                     r"\b(?:order|perform|undergo)\s+(?:a|an|the)?\s*(?:test|panel|sequenc\w*|scan|biopsy)\b|\bnext\s+steps?\b|\bwork-?up\b", re.IGNORECASE)
_RANK_ID = re.compile(r"^C(\d+)-E\d+$")


def _claim_rank(claim, packet):
    """Rank of the candidate a claim is about: the packet's own rank, or the shared C<rank> prefix of every cited id."""
    if packet.get("rank") is not None:
        return packet["rank"]
    ranks = {int(m.group(1)) for i in claim.evidence_ids for m in [_RANK_ID.match(i)] if m}
    return ranks.pop() if len(ranks) == 1 else None


_GENE = re.compile(r"\b[A-Z][A-Z0-9]{2,9}\b")
_GENERIC = {"HPO", "OMIM", "ORPHA", "DECIPHER", "NER", "SAS", "FAISS", "CAF", "GRCH38", "WES", "WGS", "DNA", "RNA", "MRI", "EEG", "AND", "THE",
            "NOT", "NO", "NOTE", "LP", "ID", "IDS", "MRR", "HP", "AF", "AC", "AN", "PASS", "SNV", "KB", "API", "UNKNOWN", "NONE"}


def parse_batch(data: Dict[str, Any]) -> Tuple[ReasoningBatch, List[str]]:
    try:
        return ReasoningBatch(**data), []
    except ValidationError as e:
        return None, [f"schema: {err['loc']} {err['msg']}" for err in e.errors()[:6]]


def _numbers(text: str) -> List[float]:
    out = []
    for m in _NUM.findall(text):
        try:
            out.append(float(m.replace("%", "").strip()))
        except ValueError:
            pass
    return out


def check_claim(claim: Claim, packet: Dict[str, Any]) -> str:
    """Return '' if the claim is grounded, else a machine-readable rejection reason."""
    by_id = {e["id"]: e for e in packet["evidence"]}
    if not claim.text.strip():
        return "empty_claim"
    if not claim.evidence_ids:
        return "no_evidence_cited"
    unknown = [i for i in claim.evidence_ids if i not in by_id]
    if unknown:
        return f"unknown_evidence_id:{unknown[0]}"
    text = _ID.sub("", claim.text)                 # evidence ids are not symbols/numbers; strip them before the content checks
    if _CITATION.search(text):
        return "citation_like_string"
    if _DIAGNOSIS.search(text):
        return "definitive_diagnosis_wording"
    if _TREATMENT.search(text):
        return "treatment_or_dosage_wording"
    if _ADVICE.search(text):
        return "test_or_management_advice"           # the system describes evidence; it never recommends tests or next steps
    for q in _QUALIFIER.finditer(text):
        # evaluative wording ('high score', 'strong similarity') is never allowed; the ORDINAL 'highest final score' is allowed only for the rank-1 candidate (the ranking key)
        if q.group(1).lower() == "highest" and re.search(r"final|overall", q.group(0), re.I) and _claim_rank(claim, packet) == 1:
            continue
        return "unsupported_score_qualifier"         # scores are uncalibrated
    cited_text = " ".join(by_id[i]["text"] + " " + str(by_id[i]["data"]) for i in claim.evidence_ids)
    ev_numbers = _numbers(cited_text) + [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", cited_text)
                                         if re.fullmatch(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", x)]
    for n in _numbers(text):
        if not any(abs(n - e) <= max(5e-4, 1e-3 * abs(e)) or abs(n - round(e, 3)) < 5e-4 or abs(n - round(e, 2)) < 5e-3 for e in ev_numbers):
            return f"ungrounded_number:{n}"
    allowed = {g.upper() for g in packet.get("genes", [])} | _GENERIC
    for tok in _GENE.findall(text):
        if tok.upper() in allowed or tok in cited_text:
            continue
        return f"ungrounded_symbol:{tok}"
    return ""


def validate_and_filter(batch: ReasoningBatch, packets_by_id: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """-> ({candidate_id: filtered explanation dict}, grounding stats)."""
    out, stats = {}, {"claims_total": 0, "claims_kept": 0, "claims_removed": 0, "removed": []}
    for c in batch.candidates:
        pk = packets_by_id.get(c.candidate_id)
        if pk is None:
            stats["removed"].append({"candidate": c.candidate_id, "reason": "unknown_candidate_id"})
            continue
        sum_ids = c.summary_evidence_ids or extract_ids(c.summary)
        expl = {"candidate_id": c.candidate_id, "summary": c.summary, "summary_evidence_ids": sum_ids}
        sum_reason = check_claim(Claim(text=c.summary, evidence_ids=sum_ids), pk)
        if sum_reason:
            expl["summary"] = None
            stats["removed"].append({"candidate": c.candidate_id, "field": "summary", "reason": sum_reason})
            stats["claims_removed"] += 1
        stats["claims_total"] += 1
        stats["claims_kept"] += 0 if sum_reason else 1
        if c.ranking_note is not None:
            stats["claims_total"] += 1
            rr = check_claim(c.ranking_note, pk)
            if rr:
                stats["claims_removed"] += 1
                stats["removed"].append({"candidate": c.candidate_id, "field": "ranking_note", "reason": rr, "text": c.ranking_note.text[:120]})
                expl["ranking_note"] = None
            else:
                stats["claims_kept"] += 1
                expl["ranking_note"] = {"text": c.ranking_note.text, "evidence_ids": c.ranking_note.evidence_ids}
        for f in CLAIM_FIELDS:
            kept = []
            for cl in getattr(c, f):
                stats["claims_total"] += 1
                r = check_claim(cl, pk)
                if r:
                    stats["claims_removed"] += 1
                    stats["removed"].append({"candidate": c.candidate_id, "field": f, "reason": r, "text": cl.text[:120]})
                else:
                    stats["claims_kept"] += 1
                    kept.append({"text": cl.text, "evidence_ids": cl.evidence_ids})
            expl[f] = kept
        out[c.candidate_id] = expl
    return out, stats
