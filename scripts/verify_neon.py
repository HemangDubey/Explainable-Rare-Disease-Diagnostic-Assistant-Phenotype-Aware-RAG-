"""Verifies a managed PostgreSQL (Neon) database for the demo WITHOUT printing the connection string or any secret.

Reads DATABASE_URL from the environment or the git-ignored .env. Accepts Neon's `postgresql://...` form (converted to
`postgresql+psycopg://`, `sslmode=require` enforced). Checks: TLS in use, migrations (Alembic head), then writes synthetic rows
(two users, a case, a scenario, a report), reads them back through a NEW engine (persistence), checks owner isolation, and deletes
every test row. Exit code 0 only if all checks pass.
    python scripts/verify_neon.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath("."))


def load_url():
    url = os.environ.get("DATABASE_URL")
    if not url and os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip("\"'")
    if not url:
        sys.exit("DATABASE_URL is not set (environment or .env).")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+"):
        sys.exit("DATABASE_URL must be a PostgreSQL URL.")
    if "sslmode=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


checks = []


def check(name, ok, detail=""):
    checks.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""), flush=True)


def main():
    os.environ["DATABASE_URL"] = load_url()
    os.environ["AUTO_MIGRATE"] = "1"
    from sqlalchemy import select, text
    from src.api import repo
    from src.auth import service
    from src.db import session as dbs
    from src.db.migrate import current_revision, head_revision, upgrade_head
    from src.db.models import User

    host = dbs.safe_url().split("@")[-1].split("/")[0]
    print("target host:", host.split(".")[0][:6] + "…" if "." in host else host)    # truncated on purpose
    try:
        with dbs.get_engine().connect() as c:
            ver = c.execute(text("select version()")).scalar()
            try:
                ssl = c.execute(text("select ssl from pg_stat_ssl where pid = pg_backend_pid()")).scalar()
            except Exception:  # noqa: BLE001
                ssl = None
        check("connected to PostgreSQL", True, ver.split(" on ")[0])
        local = any(x in os.environ["DATABASE_URL"] for x in ("localhost", "127.0.0.1", "/tmp", "pg_"))
        if local:
            print("SKIP TLS check (local database)")
        else:
            check("TLS in use (remote database)", ssl is True or (ssl is None and "sslmode=require" in os.environ["DATABASE_URL"]), "pg_stat_ssl" if ssl else "sslmode=require")
    except Exception as e:  # noqa: BLE001
        check("connected to PostgreSQL", False, type(e).__name__)
        sys.exit(1)
    upgrade_head()
    check("Alembic at head", current_revision() == head_revision(), str(current_revision()))

    tag = uuid.uuid4().hex[:6]
    pw = "Synthetic-Neon-Check-Pw1"
    emails = [f"neon-check-a-{tag}@example.test", f"neon-check-b-{tag}@example.test"]
    ids = []
    try:
        a = service.register(emails[0], pw, "A"); b = service.register(emails[1], pw, "B"); ids = [a["id"], b["id"]]
        cid = repo.save_case(a["id"], None, {"clinical_text": "Synthetic neon check.", "origin": "diagnosis"})
        repo.save_scenario(a["id"], cid, [{"op": "add", "phenotype": "HP:0001250"}], {"scenario_id": f"scn_neon{tag}"})
        repo.save_report(a["id"], cid, {"header": {"report_id": f"CR-NEON{tag}"}})
        dbs.get_engine().dispose()                           # force fresh connections: reads below come from the server, not a pool
        check("rows persisted (case, scenario, report)", repo.get_case(a["id"], cid) is not None and repo.get_scenario(a["id"], f"scn_neon{tag}") is not None
              and repo.get_report(a["id"], f"CR-NEON{tag}") is not None)
        check("owner isolation (other user sees nothing)", repo.get_case(b["id"], cid) is None and repo.get_scenario(b["id"], f"scn_neon{tag}") is None)
        check("login works", bool(service.login(emails[0], pw).get("access_token")))
    finally:
        with dbs.session_scope() as s:                       # cascades remove cases/scenarios/reports/sessions
            for u in s.scalars(select(User).where(User.email.in_(emails))).all():
                s.delete(u)
    with dbs.session_scope() as s:
        left = s.scalar(select(User).where(User.email.in_(emails)))
    check("test data removed", left is None)
    print("ALL PASS" if all(checks) else "FAILURES")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
