"""Phase 8R: real PostgreSQL backup / restore round trip on a DISPOSABLE server (embedded `pgserver` = genuine PostgreSQL 16 build).

1. start a throw-away server, apply the Alembic migrations, create synthetic users / cases / scenario / report / draft;
2. pg_dump --format=custom;
3. create MORE data after the backup (it must disappear after the restore);
4. pg_restore --clean --if-exists into the same database;
5. verify row counts, ownership isolation and that the post-backup rows are gone; remove the server.

Never touches the application's own database. Synthetic data only. Exit code 0 only if every check passes.
    python scripts/verify_postgres_backup_restore.py [--json out.json]
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
try:
    import pgserver
except ImportError:
    print("pgserver is not installed (pip install pgserver); backup/restore verification skipped")
    sys.exit(3)

BIN = os.path.join(os.path.dirname(pgserver.__file__), "pginstall", "bin")
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))


def main():
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    tmp = tempfile.mkdtemp(prefix="pg_backup_")
    srv = pgserver.get_server(os.path.join(tmp, "pgdata"))
    try:
        raw = srv.get_uri()
        os.environ["DATABASE_URL"] = raw.replace("postgresql://", "postgresql+pg8000://", 1)
        os.environ["AUTO_MIGRATE"] = "1"
        from sqlalchemy import func, select, text
        from src.api import repo
        from src.auth import service
        from src.db.migrate import upgrade_head
        from src.db.models import Case, Draft, Report, Scenario, User
        from src.db.session import get_engine, session_scope

        upgrade_head()
        with get_engine().connect() as c:
            ver = c.execute(text("select version()")).scalar()
            rev = c.execute(text("select version_num from alembic_version")).scalar()
        check("migrations applied on PostgreSQL", bool(rev), f"alembic {rev}; {ver.split(',')[0]}")

        a = service.register("backup-a@example.test", "Synthetic-Backup-Pw-1", "A")
        b = service.register("backup-b@example.test", "Synthetic-Backup-Pw-2", "B")
        ca = repo.save_case(a["id"], None, {"clinical_text": "Synthetic case A.", "origin": "diagnosis"})
        cb = repo.save_case(b["id"], None, {"clinical_text": "Synthetic case B.", "origin": "diagnosis"})
        repo.save_scenario(a["id"], ca, [{"op": "add", "phenotype": "HP:0001250"}], {"scenario_id": "scn_backup1"})
        rid = repo.save_report(a["id"], ca, {"header": {"report_id": "CR-BACKUP1"}})
        with session_scope() as s:
            s.add(Draft(id="draft-backup1", owner_id=a["id"], data={"note": "synthetic"}))

        def counts():
            with session_scope() as s:
                return {m.__tablename__: s.scalar(select(func.count()).select_from(m)) for m in (User, Case, Scenario, Report, Draft)}
        before = counts()
        check("seed data written", before["users"] == 2 and before["cases"] == 2 and before["scenarios"] == 1 and before["reports"] == 1, str(before))

        dump = os.path.join(tmp, "backup.dump")
        r = subprocess.run([os.path.join(BIN, "pg_dump"), "--format=custom", f"--file={dump}", raw], capture_output=True, text=True)
        check("pg_dump --format=custom", r.returncode == 0 and os.path.getsize(dump) > 0, f"{os.path.getsize(dump) if os.path.exists(dump) else 0} bytes")

        c_after = service.register("backup-late@example.test", "Synthetic-Backup-Pw-3", "Late")
        repo.save_case(c_after["id"], None, {"clinical_text": "Created after the backup.", "origin": "diagnosis"})
        check("post-backup rows exist before restore", counts()["users"] == 3)

        get_engine().dispose()                       # release pooled connections so the restore can drop/recreate objects
        r = subprocess.run([os.path.join(BIN, "pg_restore"), "--clean", "--if-exists", "--no-owner", f"--dbname={raw}", dump],
                           capture_output=True, text=True)
        check("pg_restore --clean --if-exists", r.returncode == 0, (r.stderr or "").strip()[:200])

        after = counts()
        check("row counts equal the backup", after == before, f"{after} vs {before}")
        with session_scope() as s:
            late = s.scalar(select(func.count()).select_from(User).where(User.email == "backup-late@example.test"))
        check("post-backup account removed by restore", late == 0)
        check("owner isolation after restore", repo.get_case(a["id"], ca) is not None and repo.get_case(b["id"], ca) is None
              and repo.get_case(a["id"], cb) is None)
        check("report restored under its owner", repo.get_report(a["id"], rid) is not None and repo.get_report(b["id"], rid) is None)
        check("login works after restore", bool(service.login("backup-a@example.test", "Synthetic-Backup-Pw-1").get("access_token")))
    finally:
        try:
            from src.db.session import get_engine
            get_engine().dispose()
        except Exception:  # noqa: BLE001
            pass
        srv.cleanup()
    ok = all(c["ok"] for c in checks)
    if out:
        json.dump({"ok": ok, "checks": checks}, open(out, "w", encoding="utf-8"), indent=1)
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
