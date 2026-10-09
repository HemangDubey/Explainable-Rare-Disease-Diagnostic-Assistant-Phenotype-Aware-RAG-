"""Owner-scoped persistence for cases, scenarios and reports. EVERY read, update and delete filters on owner_id, so a record that
belongs to another user is indistinguishable from one that does not exist (no existence oracle, no IDOR)."""
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select

from src.db.errors import guarded
from src.db.models import Case, Draft, Report, Scenario, utcnow
from src.db.session import session_scope


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


@guarded
def save_case(owner_id: str, case_id: Optional[str], ctx: Dict[str, Any]) -> str:
    """Insert (or update the caller's own) case. A client-supplied id that belongs to someone else is ignored and a fresh id is issued."""
    with session_scope() as s:
        row = s.get(Case, case_id) if case_id else None
        if row is not None and row.owner_id != owner_id:
            row = None
            case_id = None
        if row is None:
            case_id = case_id or _new_id()
            ctx = {**ctx, "case_id": case_id}
            s.add(Case(id=case_id, owner_id=owner_id, data=jsonable_encoder(ctx)))
        else:
            row.data = jsonable_encoder({**ctx, "case_id": row.id})
        return case_id


@guarded
def get_case(owner_id: str, case_id: str) -> Optional[Dict[str, Any]]:
    if not case_id:
        return None
    with session_scope() as s:
        row = s.scalar(select(Case).where(Case.id == case_id, Case.owner_id == owner_id))
        return dict(row.data) if row else None


@guarded
def list_cases(owner_id: str, limit: int = 50):
    with session_scope() as s:
        rows = s.scalars(select(Case).where(Case.owner_id == owner_id).order_by(Case.created_at.desc()).limit(limit)).all()
        return [{"case_id": r.id, "created_at": r.created_at.isoformat() + "Z"} for r in rows]


@guarded
def delete_case(owner_id: str, case_id: str) -> bool:
    """Deletes the case and everything derived from it (scenarios, reports). Drafts are separate records and are deleted on their own."""
    with session_scope() as s:
        row = s.scalar(select(Case).where(Case.id == case_id, Case.owner_id == owner_id))
        if row is None:
            return False
        s.execute(delete(Scenario).where(Scenario.case_id == case_id))
        s.execute(delete(Report).where(Report.case_id == case_id))
        s.delete(row)
        return True


@guarded
def save_scenario(owner_id: str, case_id: str, operations: Any, result: Dict[str, Any]) -> bool:
    """Stores the scenario under the caller's own case; refuses (False) if the case is not the caller's."""
    with session_scope() as s:
        if s.scalar(select(Case.id).where(Case.id == case_id, Case.owner_id == owner_id)) is None:
            return False
        s.add(Scenario(id=result["scenario_id"], case_id=case_id, owner_id=owner_id, operations=jsonable_encoder(operations), result=jsonable_encoder(result)))
        return True


@guarded
def get_scenario(owner_id: str, scenario_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        row = s.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.owner_id == owner_id))
        return dict(row.result) if row else None


@guarded
def save_report(owner_id: str, case_id: str, report: Dict[str, Any]) -> Optional[str]:
    """Stores a report for the caller's own case; returns the (possibly de-duplicated) report id, or None if the case is not the caller's."""
    with session_scope() as s:
        if s.scalar(select(Case.id).where(Case.id == case_id, Case.owner_id == owner_id)) is None:
            return None
        rid = report["header"]["report_id"]
        n = 1
        while s.get(Report, rid) is not None:         # extremely unlikely id collision across users
            rid, n = f"{report['header']['report_id']}-{n}", n + 1
        report = {**report, "header": {**report["header"], "report_id": rid}}
        s.add(Report(id=rid, case_id=case_id, owner_id=owner_id, data=jsonable_encoder(report)))
        return rid


@guarded
def get_report(owner_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        row = s.scalar(select(Report).where(Report.id == report_id, Report.owner_id == owner_id))
        return dict(row.data) if row else None


@guarded
def record_export(owner_id: str, report_id: str) -> None:
    with session_scope() as s:
        row = s.scalar(select(Report).where(Report.id == report_id, Report.owner_id == owner_id))
        if row is not None:
            row.export_count = (row.export_count or 0) + 1
            row.last_exported_at = utcnow()


@guarded
def purge_older_than(days: int) -> Dict[str, int]:
    """Retention: delete cases (and their scenarios/reports) and drafts last touched more than `days` days ago."""
    cutoff = utcnow() - timedelta(days=days)
    out = {}
    with session_scope() as s:
        old = s.scalars(select(Case.id).where(Case.updated_at < cutoff)).all()
        if old:
            s.execute(delete(Scenario).where(Scenario.case_id.in_(old)))
            s.execute(delete(Report).where(Report.case_id.in_(old)))
            s.execute(delete(Case).where(Case.id.in_(old)))
        out["cases"] = len(old)
        out["drafts"] = s.execute(delete(Draft).where(Draft.updated_at < cutoff)).rowcount or 0
    return out


@guarded
def list_case_summaries(owner_id: str, limit: int = 50):
    """Owner's cases with a short, non-clinical summary for selectors (no note text)."""
    with session_scope() as s:
        rows = s.scalars(select(Case).where(Case.owner_id == owner_id).order_by(Case.created_at.desc()).limit(limit)).all()
        out = []
        for r in rows:
            d = r.data or {}
            fc = d.get("fused_candidates") or []
            out.append({"case_id": r.id, "created_at": r.created_at.isoformat() + "Z", "origin": d.get("origin", "diagnosis"),
                        "n_findings": len(d.get("extracted_phenotypes") or []), "has_ranking": bool(fc),
                        "top_candidate": fc[0].get("disease_name") if fc else None})
        return out


@guarded
def list_scenarios(owner_id: str, case_id: str, limit: int = 30):
    with session_scope() as s:
        rows = s.scalars(select(Scenario).where(Scenario.owner_id == owner_id, Scenario.case_id == case_id)
                         .order_by(Scenario.created_at.desc()).limit(limit)).all()
        return [{"scenario_id": r.id, "created_at": r.created_at.isoformat() + "Z", "operations": r.operations,
                 "operations_applied": (r.result or {}).get("operations_applied")} for r in rows]
