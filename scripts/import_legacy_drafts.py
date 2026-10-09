"""One-off migration of Phase 5R-6R file-based drafts (data/drafts/*.json, protected by per-draft tokens) into the database.
Legacy drafts have no owner, so you must name the account that should own them.   Usage: python scripts/import_legacy_drafts.py --email you@example.org [--dir data/drafts]
Existing ids are skipped; the original files are left untouched (delete them yourself once you have checked the import)."""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, ".")
from sqlalchemy import select  # noqa: E402

from src.db.models import Draft as DraftRow, User  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.scribe.draft_schema import Draft  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--email", required=True)
ap.add_argument("--dir", default="data/drafts")
a = ap.parse_args()
imported = skipped = 0
with session_scope() as s:
    user = s.scalar(select(User).where(User.email == a.email.strip().lower()))
    if user is None:
        sys.exit("no such account; register it first")
    for path in sorted(glob.glob(os.path.join(a.dir, "*.json"))):
        try:
            raw = json.load(open(path, encoding="utf-8")).get("draft") or {}
            d = Draft(**raw)
        except Exception:
            skipped += 1
            continue
        if s.get(DraftRow, d.draft_id) is not None:
            skipped += 1
            continue
        d.saved = True
        s.add(DraftRow(id=d.draft_id, owner_id=user.id, review_state=d.review_state, data=json.loads(d.model_dump_json())))
        imported += 1
print({"imported": imported, "skipped": skipped})
