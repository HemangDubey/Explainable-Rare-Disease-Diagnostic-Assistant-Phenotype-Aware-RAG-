"""Concurrency, ownership and cascade checks of the service/repository layer against a REAL PostgreSQL server (embedded pgserver, pg8000).
Synthetic data only. Exit code 0 only if all checks pass; 3 if pgserver is unavailable."""
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, ".")
try:
    import pgserver
except ImportError:
    print("pgserver not installed; skipped")
    sys.exit(3)

srv = pgserver.get_server(tempfile.mkdtemp(prefix="pg_conc_"))
checks = {}
try:
    os.environ["DATABASE_URL"] = srv.get_uri().replace("postgresql://", "postgresql+pg8000://", 1)
    from src.db.migrate import current_revision, upgrade_head
    from src.db.session import get_engine, reset_engine
    upgrade_head()
    checks["migrated_to_head"] = current_revision() == "0001"
    from src.api import repo
    from src.auth import service
    from src.auth.service import AuthError
    from src.scribe.draft_schema import DraftUpdate
    from src.scribe.draft_store import DbDraftStore, DraftNotFound
    from src.scribe.note_structurer import NoteStructurer

    email = f"race-{os.urandom(3).hex()}@example.test"
    results = []

    def reg():
        try:
            service.register(email, "Synthetic-Passw0rd-xyz")
            results.append("ok")
        except AuthError as e:
            results.append(e.status)
    ts = [threading.Thread(target=reg) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    checks["duplicate_registration_race_exactly_one_winner"] = results.count("ok") == 1 and results.count("registration_failed") == 7

    a = service.register(f"a-{os.urandom(3).hex()}@example.test", "Synthetic-Passw0rd-xyz")["id"]
    b = service.register(f"b-{os.urandom(3).hex()}@example.test", "Synthetic-Passw0rd-xyz")["id"]
    ids, errs = [], []

    def save(i):
        try:
            ids.append(repo.save_case(a, None, {"clinical_text": f"synthetic {i}"}))
        except Exception as e:  # noqa: BLE001
            errs.append(type(e).__name__)
    ts = [threading.Thread(target=save, args=(i,)) for i in range(30)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    checks["30_concurrent_case_writes"] = not errs and len(set(ids)) == 30 and len(repo.list_cases(a, 100)) == 30
    checks["cross_user_case_read_blocked"] = repo.get_case(b, ids[0]) is None and repo.get_case(a, ids[0]) is not None
    checks["cross_user_delete_blocked"] = repo.delete_case(b, ids[0]) is False

    store = DbDraftStore()
    d = store.create(NoteStructurer(None).structure("Child has hypotonia."), a)
    codes = []

    def upd(i):
        try:
            store.update(d.draft_id, a, DraftUpdate(clinician_notes=f"note {i}"))
            codes.append("ok")
        except Exception as e:  # noqa: BLE001
            codes.append(type(e).__name__)
    ts = [threading.Thread(target=upd, args=(i,)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    checks["12_concurrent_draft_updates"] = set(codes) == {"ok"} and store.get(d.draft_id, a).clinician_notes.startswith("note ")
    try:
        store.get(d.draft_id, b)
        checks["cross_user_draft_blocked"] = False
    except DraftNotFound:
        checks["cross_user_draft_blocked"] = True

    sid = "s" + os.urandom(4).hex()
    cid = ids[1]
    checks["scenario_saved_for_own_case"] = repo.save_scenario(a, cid, [{"op": "remove"}], {"scenario_id": sid, "x": 1}) is True
    checks["scenario_refused_for_foreign_case"] = repo.save_scenario(b, cid, [], {"scenario_id": "s" + os.urandom(4).hex()}) is False
    rid = repo.save_report(a, cid, {"header": {"report_id": "CR-TEST"}, "x": 1})
    checks["report_saved_and_scoped"] = rid == "CR-TEST" and repo.get_report(b, rid) is None and repo.get_report(a, rid) is not None
    checks["cascade_delete"] = repo.delete_case(a, cid) and repo.get_scenario(a, sid) is None and repo.get_report(a, rid) is None
    from sqlalchemy import text
    with get_engine().connect() as c:
        checks["foreign_keys_present"] = c.execute(text("select count(*) from information_schema.table_constraints where constraint_type='FOREIGN KEY'")).scalar() >= 7   # 7 foreign keys are defined
        checks["indexes_present"] = c.execute(text("select count(*) from pg_indexes where indexname like 'ix_%'")).scalar() >= 8
    reset_engine()
finally:
    srv.cleanup()
print(json.dumps(checks, indent=1))
sys.exit(0 if all(checks.values()) else 1)
