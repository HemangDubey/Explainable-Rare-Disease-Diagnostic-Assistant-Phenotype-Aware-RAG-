"""Clinical Digital Twin API (Phase 7R.5). Read-mostly views over the caller's OWN stored cases; the only write is the clinician's
phenotype review (verification / status), stored inside the owner's case record. Every route requires authentication (global gate) and
filters by owner id, so other users' case ids behave as not found."""
from datetime import datetime, timezone
from typing import Callable, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api import repo
from src.api.auth_routes import current_user
from src.auth.service import AuthUser
from src.twin.anatomy import AnatomyMapper
from src.twin.builder import REVIEW_STATUSES, build_findings, build_twin

router = APIRouter(prefix="/api/twin", tags=["digital-twin"])
_ctx = {"mapper": None, "gene_record": None, "gene_lookup": None, "indigen_available": lambda: False, "gene_service": None}


def configure(hpo_terms=None, gene_record: Optional[Callable] = None, gene_lookup: Optional[Callable] = None,
              indigen_available: Optional[Callable[[], bool]] = None):
    if hpo_terms is not None:
        _ctx["mapper"] = AnatomyMapper(hpo_terms)
    _ctx["gene_record"], _ctx["gene_lookup"] = gene_record, gene_lookup
    _ctx["indigen_available"] = indigen_available or (lambda: False)


def configure_gene_service(service):
    _ctx["gene_service"] = service


def _mapper() -> AnatomyMapper:
    if _ctx["mapper"] is None:
        raise HTTPException(status_code=503, detail={"status": "unavailable", "message": "HPO ontology not loaded."})
    return _ctx["mapper"]


def _own_case(user: AuthUser, case_id: str):
    case = repo.get_case(user.id, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Case not found."})
    return case


@router.get("/cases")
def twin_cases(user: AuthUser = Depends(current_user)):
    return {"cases": repo.list_case_summaries(user.id)}


@router.get("/{case_id}")
def twin_case(case_id: str, indigen_demo: bool = False, user: AuthUser = Depends(current_user)):
    case = _own_case(user, case_id)
    svc = _ctx["gene_service"]
    tw = build_twin(case_id, case, _mapper(), _ctx["gene_record"], _ctx["gene_lookup"], scenarios=repo.list_scenarios(user.id, case_id),
                    indigen_available=bool(_ctx["indigen_available"]()),
                    gene_evidence=(lambda g: svc.evidence(g, indigen_demo=indigen_demo)) if svc else None)
    if indigen_demo and svc is not None:                  # opt-in synthetic demo: listed as its own, clearly labelled source
        from src.population.indigen_demo import DEMO_LABEL, demo_allowed
        st = svc.demo.status()
        tw["genomic"]["sources"].append({
            "source": DEMO_LABEL, "role": "synthetic values for demonstrating the IndiGen views; not evidence",
            "status": ("superseded_by_real_data" if bool(_ctx["indigen_available"]()) else st["status"]) if demo_allowed() else "disabled",
            "synthetic": True,
            "provenance": (st.get("provenance") or {}).get("statement") or st.get("reason")})
    return tw


class FindingUpdate(BaseModel):
    finding_id: str = Field(..., max_length=64)
    verified: Optional[bool] = None
    status: Optional[Literal["present", "negated", "uncertain", "pending"]] = None


class ReviewRequest(BaseModel):
    updates: List[FindingUpdate] = Field(..., max_length=200)


@router.put("/{case_id}/findings")
def review_findings(case_id: str, body: ReviewRequest, user: AuthUser = Depends(current_user)):
    """Clinician verification of extracted findings. Changes only the review state, never the pipeline's ranking."""
    case = _own_case(user, case_id)
    valid = {f["finding_id"] for f in build_findings(case, _mapper())}
    unknown = [u.finding_id for u in body.updates if u.finding_id not in valid]
    if unknown:
        raise HTTPException(status_code=422, detail={"status": "invalid_input", "message": f"Unknown finding id(s): {unknown[:5]}"})
    review = dict(case.get("phenotype_review") or {})
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for u in body.updates:
        r = dict(review.get(u.finding_id, {}))
        if u.verified is not None:
            r["verified"] = u.verified
        if u.status is not None:
            r["status"] = u.status
        r["reviewed_at"] = now
        review[u.finding_id] = r
    case["phenotype_review"] = review
    repo.save_case(user.id, case_id, case)
    return {"case_id": case_id, "findings": build_findings(case, _mapper())}


class RegionRequest(BaseModel):
    hpo_ids: List[str] = Field(..., max_length=100)


@router.post("/regions")
def regions(body: RegionRequest, user: AuthUser = Depends(current_user)):
    """Same deterministic mapping for arbitrary HPO ids (used for hypothetical counterfactual phenotypes)."""
    m = _mapper()
    return {"regions": {h: m.regions_for(h) for h in body.hpo_ids}}
