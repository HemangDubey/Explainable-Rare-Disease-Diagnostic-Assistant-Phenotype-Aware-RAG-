"""Gene-level reference evidence API (ClinVar / gnomAD global / gnomAD South Asian / IndiGen status). The SAME GeneEvidenceService
backs the Digital Twin payload, so both views share one data contract. Authenticated (global auth gate + current_user); the data are
public reference resources and contain no patient information, so no case ownership applies to these two routes."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth_routes import current_user
from src.auth.service import AuthUser

router = APIRouter(prefix="/api/genomic", tags=["genomic-evidence"])
_ctx = {"service": None}
_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def configure(service):
    _ctx["service"] = service


def _svc():
    if _ctx["service"] is None:
        raise HTTPException(status_code=503, detail={"status": "unavailable", "message": "Genomic evidence service not loaded."})
    return _ctx["service"]


def _symbol(symbol: str) -> str:
    if not _SYMBOL.match(symbol or ""):
        raise HTTPException(status_code=422, detail={"status": "invalid_input", "message": "Not a valid gene symbol."})
    return symbol


@router.get("/indigen-demo/status")
def indigen_demo_status(user: AuthUser = Depends(current_user)):
    """Whether the synthetic IndiGen demo can be shown, and whether real IndiGen data is loaded (which supersedes the demo)."""
    from src.population.indigen_demo import demo_allowed
    svc = _svc()
    return {"allowed": demo_allowed(), "real_indigen_available": bool(svc.lookup.indigen.available), "demo": svc.demo.status()}


@router.get("/indigen-demo/genes")
def indigen_demo_genes(symbols: str = Query(..., max_length=400), user: AuthUser = Depends(current_user)):
    """Gene-level synthetic demo values for several genes (used by the workspace evidence cards). Display only."""
    from src.population.indigen_demo import DEMO_LABEL, demo_allowed
    syms = [_symbol(x.strip()) for x in symbols.split(",") if x.strip()][:20]
    svc = _svc()
    if svc.lookup.indigen.available:
        return {"label": DEMO_LABEL, "status": "superseded_by_real_data", "genes": {}}
    if not demo_allowed():
        return {"label": DEMO_LABEL, "status": "disabled", "genes": {}}
    out = {}
    for s in syms:
        g = svc.demo.gene(svc.resolve(s)["symbol"] or s)
        out[s] = {k: g.get(k) for k in ("status", "cumulative_af", "n_variants", "n_variants_nonzero", "reason")}
    return {"label": DEMO_LABEL, "status": "available" if svc.demo.available else "unavailable", "synthetic": True,
            "provenance": svc.demo.provenance if svc.demo.available else None, "genes": out}


@router.get("/gene/{symbol}")
def gene_evidence(symbol: str, indigen_demo: bool = False, user: AuthUser = Depends(current_user)):
    return _svc().evidence(_symbol(symbol), indigen_demo=indigen_demo)


@router.post("/gene/{symbol}/ingest")
def gene_ingest(symbol: str, force: Optional[bool] = False, indigen_demo: bool = False, user: AuthUser = Depends(current_user)):
    """Fetch real gnomAD v4.1 exome counts for one ClinVar gene (official public VCFs, HTTP range reads; idempotent), then return
    the refreshed evidence. Genes unknown to ClinVar are rejected as not_found without any network access."""
    svc = _svc()
    res = svc.ingest(_symbol(symbol), force=bool(force))
    if res["status"] == "busy":
        raise HTTPException(status_code=503, detail={"status": "busy", "message": res["reason"], "retryable": True})
    ev = svc.evidence(symbol, indigen_demo=indigen_demo)
    return {"ingest": {k: v for k, v in res.items() if k != "resolution"}, "evidence": ev}
