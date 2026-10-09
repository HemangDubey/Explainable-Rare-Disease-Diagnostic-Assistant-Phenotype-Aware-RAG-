"""Phase 7R: authentication, ownership isolation, persistence, concurrency and database-failure tests.

REAL integration: real FastAPI app, real SQLite database (temp file), real Alembic migration, real NER/HPO/FAISS/ranking pipeline, real argon2.
MOCKED: only the database-failure tests patch the session layer. All data is synthetic. See tests/test_restart_integration.py for the
real process-restart test and tests/test_postgres_integration.py for PostgreSQL.
"""
import os
import sys
import threading
import unittest
from datetime import timedelta
from unittest import mock

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import PASSWORD, authed_client, register_and_login, use_temp_database  # noqa: E402

use_temp_database()
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
PROTECTED = [("post", "/api/retrieve", {"clinical_text": TEXT}), ("post", "/api/rank", {"clinical_text": TEXT}), ("post", "/api/diagnose", {"clinical_text": TEXT}),
             ("post", "/api/reason", {"case_id": "x"}), ("post", "/api/explain", {"case_id": "x", "disease_id": "d"}), ("post", "/api/differential", {"case_id": "x"}),
             ("post", "/api/copilot", {"query": "Why was it ranked first?"}), ("post", "/api/input/validate", {"text": TEXT}), ("post", "/api/input/enhance", {"text": TEXT}),
             ("post", "/api/scribe/draft", {"clinical_text": TEXT}), ("get", "/api/scribe/draft/abc", None), ("put", "/api/scribe/draft/abc", {}), ("delete", "/api/scribe/draft/abc", None),
             ("post", "/api/counterfactual/scenario", {"clinical_text": TEXT}), ("get", "/api/counterfactual/scenario/abc", None), ("post", "/api/counterfactual", {"operation": "remove"}),
             ("get", "/api/counterfactual/abc", None), ("post", "/api/report/generate", {"clinical_text": TEXT}), ("get", "/api/report/abc", None), ("get", "/api/report/abc/export", None),
             ("get", "/api/evidence/profile/OMIM:1", None), ("get", "/api/evidence/matrix/OMIM:1", None), ("delete", "/api/case/abc", None), ("get", "/api/cases", None),
             ("post", "/api/literature/search", {"disease_id": "OMIM:1", "disease_name": "x"}), ("get", "/api/literature/123", None), ("post", "/api/scribe", {"clinical_text": TEXT}),
             ("get", "/api/auth/me", None), ("post", "/api/auth/logout", None)]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.api import main
        cls.main = main
        cls._ctx = TestClient(main.app, raise_server_exceptions=False)
        cls.c = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()
        self.c.headers.pop("Authorization", None)

    def fresh(self, **kw):
        """A separate client object (no shared headers) logged in as a new synthetic user."""
        cl = TestClient(self.main.app, raise_server_exceptions=False)
        u = authed_client(cl, **kw)
        return cl, u


class TestRegistrationAndLogin(Base):
    def test_register_login_me_logout(self):
        u = register_and_login(self.c)
        me = self.c.get("/api/auth/me", headers=u["headers"])
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], u["email"])
        self.assertNotIn("password", me.text.lower())
        self.assertEqual(self.c.post("/api/auth/logout", headers=u["headers"]).status_code, 200)
        r = self.c.get("/api/auth/me", headers=u["headers"])
        self.assertEqual(r.status_code, 401)                              # logout invalidates the session server-side
        self.assertEqual(r.json()["detail"]["status"], "session_expired")

    def test_passwords_are_hashed_with_argon2id_never_plaintext(self):
        u = register_and_login(self.c)
        from src.db.models import User
        from src.db.session import session_scope
        with session_scope() as s:
            row = s.scalar(select(User).where(User.email == u["email"]))
            self.assertTrue(row.password_hash.startswith("$argon2id$"))
            self.assertNotIn(PASSWORD, row.password_hash)
        from src.auth import security as sec
        self.assertTrue(sec.verify_password(row.password_hash, PASSWORD))
        self.assertFalse(sec.verify_password(row.password_hash, PASSWORD + "x"))
        self.assertNotEqual(sec.hash_password(PASSWORD), sec.hash_password(PASSWORD))      # per-hash salt

    def test_session_tokens_are_stored_only_as_digests(self):
        u = register_and_login(self.c)
        from src.db.models import AuthSession
        from src.db.session import session_scope
        with session_scope() as s:
            hashes = [r.token_hash for r in s.scalars(select(AuthSession)).all()]
        self.assertNotIn(u["token"], hashes)
        from src.auth.security import token_digest
        self.assertIn(token_digest(u["token"]), hashes)

    def test_credential_validation(self):
        bad = [("not-an-email", PASSWORD), ("a@b.test", "short"), ("a@b.test", "x" * 200), ("c@d.test", "aaaaaaaaaaaaaaaa"), ("someone@d.test", "my-someone-password-1")]
        for email, pw in bad:
            r = self.c.post("/api/auth/register", json={"email": email, "password": pw})
            self.assertEqual(r.status_code, 422, (email, pw[:10]))
            self.assertEqual(r.json()["detail"]["status"], "invalid_input")
        self.assertEqual(self.c.post("/api/auth/register", json={"email": "x@y.test"}).status_code, 422)     # schema validation

    def test_duplicate_registration_and_generic_login_errors(self):
        u = register_and_login(self.c)
        dup = self.c.post("/api/auth/register", json={"email": u["email"].upper(), "password": PASSWORD})
        self.assertEqual(dup.status_code, 409)
        wrong = self.c.post("/api/auth/login", json={"email": u["email"], "password": "Wrong-password-123"})
        unknown = self.c.post("/api/auth/login", json={"email": "nobody-here@example.test", "password": "Wrong-password-123"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())                    # identical body: no account-existence oracle
        self.assertNotIn("exist", wrong.text.lower())

    def test_account_lockout_after_repeated_failures(self):
        u = register_and_login(self.c)
        with mock.patch.dict(os.environ, {"LOGIN_MAX_FAILURES": "3"}):
            for _ in range(3):
                self.assertEqual(self.c.post("/api/auth/login", json={"email": u["email"], "password": "Wrong-password-123"}).status_code, 401)
            ok_pw = self.c.post("/api/auth/login", json={"email": u["email"], "password": PASSWORD})
            self.assertEqual(ok_pw.status_code, 401)                       # locked even with the right password, same generic error
            self.assertEqual(ok_pw.json()["detail"]["status"], "invalid_credentials")
        from src.db.models import User
        from src.db.session import session_scope
        with session_scope() as s:                                          # simulate the lock period passing
            s.scalar(select(User).where(User.email == u["email"])).locked_until = None
        self.assertEqual(self.c.post("/api/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code, 200)

    def test_auth_endpoints_are_rate_limited(self):
        old = self.main.AUTH_RATE_LIMIT_PER_MIN
        try:
            self.main.AUTH_RATE_LIMIT_PER_MIN = 4
            codes = [self.c.post("/api/auth/login", json={"email": "ratelimit@example.test", "password": "Wrong-password-123"}).status_code for _ in range(8)]
            self.assertIn(429, codes)
            self.assertEqual(codes[:4], [401] * 4)
            r = self.c.post("/api/auth/login", json={"email": "ratelimit@example.test", "password": "x"})
            self.assertEqual(r.json()["detail"]["status"], "rate_limited")
        finally:
            self.main.AUTH_RATE_LIMIT_PER_MIN = old

    def test_registration_can_be_closed(self):
        with mock.patch.dict(os.environ, {"ALLOW_REGISTRATION": "0"}):
            self.assertEqual(self.c.post("/api/auth/register", json={"email": "closed@example.test", "password": PASSWORD}).status_code, 403)


class TestSessionLifetime(Base):
    def _sessions(self, token):
        from src.auth.security import token_digest
        from src.db.models import AuthSession
        from src.db.session import session_scope
        return session_scope, AuthSession, token_digest(token)

    def test_missing_invalid_and_malformed_credentials(self):
        for headers in ({}, {"Authorization": "Bearer not-a-real-token"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}, {"Authorization": "Bearer " + "x" * 500}):
            r = self.c.get("/api/auth/me", headers=headers)
            self.assertEqual(r.status_code, 401, headers)
            self.assertEqual(r.headers.get("www-authenticate"), "Bearer")

    def test_idle_expiry_and_sliding_extension(self):
        u = register_and_login(self.c)
        scope, AS, dig = self._sessions(u["token"])
        with scope() as s:
            row = s.scalar(select(AS).where(AS.token_hash == dig))
            from src.db.models import utcnow
            row.expires_at = utcnow() + timedelta(seconds=30)             # nearly idle-expired
        self.assertEqual(self.c.get("/api/auth/me", headers=u["headers"]).status_code, 200)      # activity slides the idle window
        with scope() as s:
            self.assertGreater(s.scalar(select(AS).where(AS.token_hash == dig)).expires_at, utcnow() + timedelta(minutes=30))
            s.scalar(select(AS).where(AS.token_hash == dig)).expires_at = utcnow() - timedelta(seconds=1)
        r = self.c.get("/api/auth/me", headers=u["headers"])
        self.assertEqual((r.status_code, r.json()["detail"]["status"]), (401, "session_expired"))

    def test_absolute_expiry_cannot_be_extended(self):
        u = register_and_login(self.c)
        scope, AS, dig = self._sessions(u["token"])
        from src.db.models import utcnow
        with scope() as s:
            s.scalar(select(AS).where(AS.token_hash == dig)).absolute_expires_at = utcnow() - timedelta(seconds=1)
        self.assertEqual(self.c.get("/api/auth/me", headers=u["headers"]).status_code, 401)

    def test_expired_session_is_rejected_on_every_protected_route(self):
        u = register_and_login(self.c)
        scope, AS, dig = self._sessions(u["token"])
        from src.db.models import utcnow
        with scope() as s:
            s.scalar(select(AS).where(AS.token_hash == dig)).expires_at = utcnow() - timedelta(seconds=1)
        for m, path, body in PROTECTED:
            r = getattr(self.c, m)(path, headers=u["headers"], **({"json": body} if body is not None else {}))
            self.assertEqual(r.status_code, 401, path)

    def test_every_protected_route_requires_authentication(self):
        for m, path, body in PROTECTED:
            r = getattr(self.c, m)(path, **({"json": body} if body is not None else {}))
            self.assertEqual(r.status_code, 401, path)
        self.assertEqual(self.c.get("/").status_code, 200)                  # health is public and carries no clinical data
        self.assertNotIn("password", self.c.get("/").text.lower())


class TestOwnershipIsolation(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A, cls.ua = TestClient(cls.main.app, raise_server_exceptions=False), None
        cls.ua = authed_client(cls.A)
        cls.B = TestClient(cls.main.app, raise_server_exceptions=False)
        cls.ub = authed_client(cls.B)
        d = cls.A.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3}).json()
        cls.case_id, cls.diag = d["case_id"], d
        cls.scen = cls.A.post("/api/counterfactual/scenario", json={"case_id": cls.case_id, "operations": [{"op": "remove", "phenotype": "HP:0001250"}]}).json()
        cls.report = cls.A.post("/api/report/generate", json={"case_id": cls.case_id}).json()
        cls.draft = cls.A.post("/api/scribe/draft", json={"clinical_text": TEXT}).json()

    def test_owner_can_use_everything(self):
        A, cid = self.A, self.case_id
        self.assertNotIn("case_token", self.diag)                           # capability tokens are gone; identity is the credential
        self.assertEqual(A.post("/api/differential", json={"case_id": cid}).status_code, 200)
        self.assertEqual(A.post("/api/counterfactual/scenario", json={"case_id": cid, "operations": []}).status_code, 200)
        self.assertEqual(A.get(f"/api/counterfactual/scenario/{self.scen['scenario_id']}").status_code, 200)
        rid = self.report["header"]["report_id"]
        self.assertEqual(A.get(f"/api/report/{rid}").status_code, 200)
        self.assertEqual(A.get(f"/api/report/{rid}/export").status_code, 200)
        self.assertEqual(A.get(f"/api/scribe/draft/{self.draft['draft_id']}").status_code, 200)
        self.assertIn(cid, [c["case_id"] for c in A.get("/api/cases").json()["cases"]])

    def test_other_user_cannot_read_or_modify_known_ids(self):
        B, cid = self.B, self.case_id
        rid, sid, did = self.report["header"]["report_id"], self.scen["scenario_id"], self.draft["draft_id"]
        self.assertEqual(B.get(f"/api/counterfactual/scenario/{sid}").status_code, 404)
        self.assertEqual(B.get(f"/api/report/{rid}").status_code, 404)
        self.assertEqual(B.get(f"/api/report/{rid}/export").status_code, 404)
        self.assertEqual(B.get(f"/api/scribe/draft/{did}").status_code, 404)
        self.assertEqual(B.put(f"/api/scribe/draft/{did}", json={"clinician_notes": "tamper"}).status_code, 404)
        self.assertEqual(B.delete(f"/api/scribe/draft/{did}").status_code, 404)
        self.assertEqual(B.delete(f"/api/case/{cid}").status_code, 404)
        self.assertEqual(B.post("/api/counterfactual/scenario", json={"case_id": cid, "operations": []}).status_code, 404)
        self.assertEqual(B.post("/api/report/generate", json={"case_id": cid}).status_code, 400)       # never falls back to another user's case
        self.assertEqual(B.post("/api/reason", json={"case_id": cid}).status_code, 400)
        self.assertEqual(B.get(f"/api/counterfactual/{cid}").status_code, 404)
        cop = B.post("/api/copilot", json={"case_id": cid, "query": "Why was the first candidate ranked first?"}).json()
        self.assertEqual(cop["provider"]["status"], "no_case_context")
        self.assertNotIn("hypotonia", str(cop).lower())
        self.assertNotIn(cid, [c["case_id"] for c in B.get("/api/cases").json()["cases"]])
        # the owner's records are untouched by every attempt above
        self.assertEqual(self.A.get(f"/api/scribe/draft/{did}").json()["clinician_notes"], "")
        self.assertEqual(self.A.get(f"/api/report/{rid}").status_code, 200)

    def test_client_supplied_case_id_cannot_overwrite_another_users_case(self):
        r = self.B.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3, "case_id": self.case_id}).json()
        self.assertNotEqual(r["case_id"], self.case_id)                     # a fresh id was issued instead of hijacking
        from src.api import repo
        mine = repo.get_case(self.ua["user"]["id"], self.case_id)
        self.assertIsNotNone(mine)

    def test_records_are_stored_under_the_owner_id(self):
        from src.db.models import Case, Draft, Report, Scenario
        from src.db.session import session_scope
        with session_scope() as s:
            self.assertEqual(s.get(Case, self.case_id).owner_id, self.ua["user"]["id"])
            self.assertEqual(s.get(Scenario, self.scen["scenario_id"]).case_id, self.case_id)
            self.assertEqual(s.get(Scenario, self.scen["scenario_id"]).owner_id, self.ua["user"]["id"])
            self.assertEqual(s.get(Report, self.report["header"]["report_id"]).owner_id, self.ua["user"]["id"])
            self.assertEqual(s.get(Draft, self.draft["draft_id"]).owner_id, self.ua["user"]["id"])

    def test_scenario_is_reproducible_and_labelled_hypothetical(self):
        s = self.A.get(f"/api/counterfactual/scenario/{self.scen['scenario_id']}").json()
        self.assertTrue(s["hypothetical"])
        self.assertIn("HYPOTHETICAL", s["scenario_label"])
        self.assertEqual(s["operations"][0]["status"], "applied")
        from src.db.models import Scenario
        from src.db.session import session_scope
        with session_scope() as sess:
            self.assertEqual(sess.get(Scenario, s["scenario_id"]).operations[0]["phenotype"], "HP:0001250")

    def test_ranking_is_unchanged_by_the_database_layer(self):
        again = self.A.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3}).json()
        self.assertEqual([c["disease_id"] for c in again["fused_candidates"]], [c["disease_id"] for c in self.diag["fused_candidates"]])
        self.assertEqual([c["final_score"] for c in again["fused_candidates"]], [c["final_score"] for c in self.diag["fused_candidates"]])
        w = self.diag["fused_candidates"][0]["score_breakdown"]["weights"]
        self.assertEqual((w["w_phenotype"], w["w_retrieval"], w["w_population"]), (0.2, 0.8, 0.0))

    def test_case_deletion_removes_derived_records_only_for_the_owner(self):
        cl, u = self.fresh()
        d = cl.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3}).json()
        cid = d["case_id"]
        sid = cl.post("/api/counterfactual/scenario", json={"case_id": cid, "operations": []}).json()["scenario_id"]
        rid = cl.post("/api/report/generate", json={"case_id": cid}).json()["header"]["report_id"]
        draft_id = cl.post("/api/scribe/draft", json={"clinical_text": TEXT}).json()["draft_id"]
        self.assertEqual(self.B.delete(f"/api/case/{cid}").status_code, 404)                 # someone else cannot delete it
        self.assertEqual(cl.delete(f"/api/case/{cid}").status_code, 200)
        self.assertEqual(cl.get(f"/api/counterfactual/scenario/{sid}").status_code, 404)
        self.assertEqual(cl.get(f"/api/report/{rid}").status_code, 404)
        self.assertEqual(cl.delete(f"/api/case/{cid}").status_code, 404)
        self.assertEqual(cl.get(f"/api/scribe/draft/{draft_id}").status_code, 200)           # drafts are independent records
        self.assertEqual(cl.delete(f"/api/scribe/draft/{draft_id}").status_code, 200)
        self.assertEqual(cl.get(f"/api/scribe/draft/{draft_id}").status_code, 404)

    def test_draft_semantics_survive_persistence(self):
        d = self.A.post("/api/scribe/draft", json={"clinical_text": "Mother reports that the child does not have seizures. Child has hypotonia. Mother has epilepsy."}).json()
        got = self.A.get(f"/api/scribe/draft/{d['draft_id']}").json()
        st = {p["mention"].lower(): p["status"] for p in got["phenotypes"]}
        self.assertEqual(st.get("seizures"), "negated")
        self.assertEqual(st.get("hypotonia"), "present")
        self.assertEqual(st.get("epilepsy"), "relative_finding")
        self.assertEqual(got["status"], "Draft — clinician review required")
        self.assertNotIn("seizure", got["diagnosis_input"].lower())
        up = self.A.put(f"/api/scribe/draft/{d['draft_id']}", json={"review_state": "reviewed"}).json()
        self.assertEqual(up["status"], "Draft — clinician-reviewed (not signed or approved)")
        self.assertNotRegex(up["status"].lower(), r"signed by|approved by|final")

    def test_report_export_is_escaped_and_owner_scoped(self):
        from src.api import repo
        evil = "<script>alert(1)</script> hypotonia"
        cid = repo.save_case(self.ua["user"]["id"], None, {"clinical_text": evil, "fused_candidates": [{"disease_id": "D:1", "disease_name": "<img src=x onerror=alert(2)>", "final_score": 0.5}]})
        rid = self.A.post("/api/report/generate", json={"case_id": cid}).json()["header"]["report_id"]
        html = self.A.get(f"/api/report/{rid}/export").text
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertEqual(self.B.get(f"/api/report/{rid}/export").status_code, 404)
        from src.db.models import Report
        from src.db.session import session_scope
        with session_scope() as s:
            self.assertGreaterEqual(s.get(Report, rid).export_count, 1)             # export metadata recorded


class TestPersistence(Base):
    def test_state_is_in_the_database_not_in_process_memory(self):
        cl, u = self.fresh()
        cid = cl.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3}).json()["case_id"]
        did = cl.post("/api/scribe/draft", json={"clinical_text": TEXT}).json()["draft_id"]
        from src.db import session as dbs
        dbs.reset_engine()                                                  # drop every connection and cached handle
        self.assertEqual(cl.get("/api/auth/me").status_code, 200)           # the SESSION survived
        self.assertEqual(cl.post("/api/differential", json={"case_id": cid}).status_code, 200)     # the CASE survived
        self.assertEqual(cl.get(f"/api/scribe/draft/{did}").status_code, 200)                       # the DRAFT survived
        self.assertFalse(hasattr(self.main, "case_store"))

    def test_migration_is_current_and_foreign_keys_enforced(self):
        from src.db.migrate import head_revision, schema_is_current
        from src.db.session import get_engine
        self.assertTrue(schema_is_current())
        self.assertEqual(head_revision(), "0001")
        with get_engine().connect() as c:
            self.assertEqual(c.execute(text("PRAGMA foreign_keys")).scalar(), 1)
        from src.db.models import Case
        from src.db.session import session_scope
        with self.assertRaises(Exception):
            with session_scope() as s:
                s.add(Case(id="orphan", owner_id="no-such-user", data={}))     # FK violation is rejected

    def test_health_reports_database_without_secrets(self):
        h = self.c.get("/").json()
        self.assertEqual(h["database"]["status"], "ok")
        self.assertNotIn("sqlite", str(h).lower())
        self.assertNotIn("password", str(h).lower())

    def test_retention_purge_deletes_old_records(self):
        from src.api import repo
        from src.db.models import Case
        from src.db.session import session_scope
        cl, u = self.fresh()
        cid = repo.save_case(u["user"]["id"], None, {"clinical_text": "synthetic"})
        with session_scope() as s:
            from src.db.models import utcnow
            s.get(Case, cid).updated_at = utcnow() - timedelta(days=100)
        out = repo.purge_older_than(30)
        self.assertGreaterEqual(out["cases"], 1)
        self.assertIsNone(repo.get_case(u["user"]["id"], cid))


class TestConcurrency(Base):
    def test_concurrent_case_and_draft_writes(self):
        cl, u = self.fresh()
        from src.api import repo
        ids, errors = [], []

        def work(i):
            try:
                ids.append(repo.save_case(u["user"]["id"], None, {"clinical_text": f"synthetic note {i}"}))
            except Exception as e:  # noqa: BLE001
                errors.append(type(e).__name__)
        ts = [threading.Thread(target=work, args=(i,)) for i in range(24)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        self.assertEqual(len(set(ids)), 24)
        self.assertEqual(len(repo.list_cases(u["user"]["id"], limit=100)), 24)

    def test_concurrent_duplicate_registration_creates_exactly_one_account(self):
        email = "race-" + os.urandom(3).hex() + "@example.test"
        codes = []

        def reg():
            r = TestClient(self.main.app).post("/api/auth/register", json={"email": email, "password": PASSWORD})
            codes.append(r.status_code)
        ts = [threading.Thread(target=reg) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(codes.count(201), 1, codes)
        self.assertEqual(codes.count(409), 5, codes)

    def test_concurrent_updates_to_one_draft_do_not_corrupt_it(self):
        cl, u = self.fresh()
        did = cl.post("/api/scribe/draft", json={"clinical_text": TEXT}).json()["draft_id"]
        codes = []

        def upd(i):
            codes.append(TestClient(self.main.app).put(f"/api/scribe/draft/{did}", headers=u["headers"], json={"clinician_notes": f"note {i}"}).status_code)
        ts = [threading.Thread(target=upd, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(set(codes), {200})
        self.assertTrue(cl.get(f"/api/scribe/draft/{did}").json()["clinician_notes"].startswith("note "))


class TestDatabaseFailure(Base):
    """MOCKED: the session layer is patched to simulate an unavailable database."""

    def test_unavailable_database_gives_503_not_a_crash_or_leak(self):
        cl, u = self.fresh()
        boom = OperationalError("SELECT secret_sql", {"p": "patient text"}, Exception("conn refused"))
        with mock.patch("src.db.session.get_engine", side_effect=boom):
            r = cl.get("/api/auth/me")
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json()["detail"]["status"], "database_unavailable")
            self.assertNotIn("secret_sql", r.text)
            self.assertNotIn("patient text", r.text)
            self.assertEqual(self.c.post("/api/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code, 503)
            h = self.c.get("/")
            self.assertEqual(h.status_code, 200)
            self.assertEqual(h.json()["database"]["status"], "unavailable")
        self.assertEqual(cl.get("/api/auth/me").status_code, 200)            # recovers when the database returns

    def test_write_failure_while_saving_a_case_is_reported_as_503(self):
        cl, u = self.fresh()
        from src.db.errors import StorageError
        with mock.patch("src.api.repo.save_case", side_effect=StorageError("OperationalError")):
            r = cl.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 3})
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json()["detail"]["status"], "database_unavailable")

    def test_draft_save_failure_is_visible_and_not_claimed_as_saved(self):
        cl, u = self.fresh()
        from src.db.errors import StorageError
        with mock.patch("src.scribe.draft_store.DbDraftStore._create", side_effect=StorageError("x")):
            d = cl.post("/api/scribe/draft", json={"clinical_text": TEXT}).json()
        self.assertFalse(d["saved"])
        self.assertEqual(d["persistence"]["status"], "persistence_failure")


class TestProductionConfiguration(unittest.TestCase):
    def test_invalid_production_configuration_refuses_to_start(self):
        from src.api import main
        with mock.patch.object(main, "PRODUCTION", True), mock.patch.dict(os.environ, {"DATABASE_URL": "", "CORS_ALLOW_ORIGINS": ""}, clear=False):
            with self.assertRaises(RuntimeError) as cm:
                main._init_database()
            self.assertIn("DATABASE_URL", str(cm.exception))
            self.assertIn("CORS_ALLOW_ORIGINS", str(cm.exception))
        with mock.patch.object(main, "PRODUCTION", True), mock.patch.object(main, "CORS_ORIGINS", ["http://localhost:5173"]), \
                mock.patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "http://localhost:5173"}):
            with self.assertRaises(RuntimeError) as cm:
                main._init_database()
            self.assertIn("localhost", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
