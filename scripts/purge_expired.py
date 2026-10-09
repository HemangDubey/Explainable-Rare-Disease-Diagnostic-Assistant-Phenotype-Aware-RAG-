"""Retention / cleanup job: deletes cases (with their scenarios and reports) and drafts not updated for N days, plus expired or revoked sessions.
Run it from cron / a scheduler, or set RETENTION_DAYS so the API does it every 6 hours.   Usage: python scripts/purge_expired.py --days 90 [--dry-run]"""
import argparse
import sys
from datetime import timedelta

sys.path.insert(0, ".")
from sqlalchemy import func, select  # noqa: E402

from src.api import repo  # noqa: E402
from src.auth.service import purge_sessions  # noqa: E402
from src.db.models import Case, Draft, utcnow  # noqa: E402
from src.db.session import safe_url, session_scope  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, required=True)
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
if a.days < 1:
    sys.exit("--days must be >= 1")
cutoff = utcnow() - timedelta(days=a.days)
print("database:", safe_url())
if a.dry_run:
    with session_scope() as s:
        print({"cases_to_delete": s.scalar(select(func.count()).select_from(Case).where(Case.updated_at < cutoff)),
               "drafts_to_delete": s.scalar(select(func.count()).select_from(Draft).where(Draft.updated_at < cutoff))})
else:
    print({"deleted": repo.purge_older_than(a.days), "sessions_removed": purge_sessions()})
