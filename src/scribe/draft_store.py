"""Database-backed, owner-scoped persistence for reviewed scribe drafts (Phase 7R; replaces the file store + draft tokens).

Only the authenticated owner can read, update or delete a draft; another user's draft is reported as not found. Logs contain only
draft ids and counts, never note text.
"""
import logging
import uuid
from typing import Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from src.db.errors import StorageError, guarded
from src.db.models import Draft as DraftRow, utcnow
from src.db.session import session_scope
from src.scribe.draft_schema import Draft, DraftUpdate

logger = logging.getLogger("scribe_drafts")


class DraftNotFound(Exception):
    pass


class PersistenceError(Exception):
    """The draft could not be stored or read (mapped to the API's persistence_failure status)."""


class DbDraftStore:
    def create(self, draft: Draft, owner_id: str) -> Draft:
        draft.saved = True
        draft.updated_at = utcnow().isoformat() + "Z"
        try:
            self._create(draft, owner_id)
        except StorageError as e:
            raise PersistenceError(str(e)) from None
        logger.info("draft %s created (%d statements)", draft.draft_id, len(draft.statements))
        return draft

    @guarded
    def _create(self, draft: Draft, owner_id: str) -> None:
        with session_scope() as s:
            s.add(DraftRow(id=draft.draft_id, owner_id=owner_id, review_state=draft.review_state, data=jsonable_encoder(draft.model_dump())))

    @guarded
    def _load(self, draft_id: str, owner_id: str) -> Optional[Draft]:
        with session_scope() as s:
            row = s.scalar(select(DraftRow).where(DraftRow.id == draft_id, DraftRow.owner_id == owner_id))
            return Draft(**row.data) if row else None

    def get(self, draft_id: str, owner_id: str) -> Draft:
        try:
            d = self._load(draft_id, owner_id)
        except StorageError as e:
            raise PersistenceError(str(e)) from None
        if d is None:
            raise DraftNotFound(draft_id)
        return d

    @guarded
    def _write(self, draft_id: str, owner_id: str, upd: DraftUpdate):
        with session_scope() as s:
            row = s.scalar(select(DraftRow).where(DraftRow.id == draft_id, DraftRow.owner_id == owner_id).with_for_update())
            if row is None:
                return None
            draft = Draft(**row.data)
            apply_update(draft, upd)
            draft.saved = True
            draft.updated_at = utcnow().isoformat() + "Z"
            row.data, row.review_state = jsonable_encoder(draft.model_dump()), draft.review_state
            return draft

    def update(self, draft_id: str, owner_id: str, upd: DraftUpdate) -> Draft:
        try:
            d = self._write(draft_id, owner_id, upd)
        except StorageError as e:
            raise PersistenceError(str(e)) from None
        if d is None:
            raise DraftNotFound(draft_id)
        logger.info("draft %s updated", draft_id)
        return d

    @guarded
    def _remove(self, draft_id: str, owner_id: str) -> bool:
        with session_scope() as s:
            row = s.scalar(select(DraftRow).where(DraftRow.id == draft_id, DraftRow.owner_id == owner_id))
            if row is None:
                return False
            s.delete(row)
            return True

    def delete(self, draft_id: str, owner_id: str) -> None:
        try:
            ok = self._remove(draft_id, owner_id)
        except StorageError as e:
            raise PersistenceError(str(e)) from None
        if not ok:
            raise DraftNotFound(draft_id)
        logger.info("draft %s deleted", draft_id)


def apply_update(draft: Draft, upd: DraftUpdate) -> Draft:
    """Clinician edits. Never changes provenance: edited statements keep their source span and are flagged `edited`."""
    sec_items = [it for s in draft.sections.values() for it in s.items]
    for e in upd.statements or []:
        for st in [s for s in draft.statements if s.id == e.get("id")] + [it for it in sec_items if it.id == e.get("id")]:
            if "text" in e and isinstance(e["text"], str) and e["text"].strip() and e["text"] != st.text:
                st.text, st.edited, st.origin = e["text"], True, "clinician_edit"
                st.verified = False if "verified" not in e else bool(e["verified"])
            if "verified" in e:
                st.verified = bool(e["verified"])
            if "removed" in e:
                st.removed = bool(e["removed"])
    for e in upd.phenotypes or []:
        for p in draft.phenotypes:
            if p.id == e.get("id"):
                if "verified" in e:
                    p.verified = bool(e["verified"])
                if e.get("status") in ("present", "negated", "uncertain"):
                    p.status = e["status"]
    if upd.clinician_notes is not None:
        draft.clinician_notes = upd.clinician_notes[:5000]
    if upd.review_state is not None:
        draft.review_state = upd.review_state
    draft.status = "Draft — clinician review required" if draft.review_state == "draft" else "Draft — clinician-reviewed (not signed or approved)"
    live = [p.mention for p in draft.phenotypes if p.status == "present" and p.subject == "patient"
            and not next((s.removed for s in draft.statements if s.id == p.statement_id), False)]
    draft.diagnosis_input = ("Patient presents with " + ", ".join(dict.fromkeys(live)) + ".") if live else ""
    return draft
