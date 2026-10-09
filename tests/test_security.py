"""Security tests (Phase 6R, updated for Phase 7R authentication): CORS allowlist, size and rate limits, safe errors, security headers,
frontend credential handling and secret hygiene. Real app + real temp SQLite database. Cross-user isolation lives in tests/test_auth_db.py."""
import os
import sys
import unittest

sys.path.append(os.path.abspath("."))
os.environ["CORS_ALLOW_ORIGINS"] = "http://localhost:5173,https://app.example.org"
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from fastapi.testclient import TestClient  # noqa: E402

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


class TestApiProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.api import main
        cls.main = main
        cls._ctx = TestClient(main.app, raise_server_exceptions=False)
        cls.c = cls._ctx.__enter__()
        authed_client(cls.c)

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()

    def test_cors_allowlist(self):
        pre = lambda o: self.c.options("/api/diagnose", headers={"Origin": o, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"})
        ok = pre("https://app.example.org")
        self.assertEqual(ok.headers.get("access-control-allow-origin"), "https://app.example.org")
        bad = pre("https://evil.example.com")
        self.assertIsNone(bad.headers.get("access-control-allow-origin"))
        self.assertNotEqual(ok.headers.get("access-control-allow-origin"), "*")
        self.assertIsNone(ok.headers.get("access-control-allow-credentials"))
        self.assertNotIn("*", self.main.CORS_ORIGINS)
        self.assertNotIn("x-case-token", (ok.headers.get("access-control-allow-headers") or "").lower())     # the old capability headers are gone

    def test_preflight_does_not_require_authentication(self):
        r = TestClient(self.main.app).options("/api/diagnose", headers={"Origin": "https://app.example.org", "Access-Control-Request-Method": "POST"})
        self.assertEqual(r.status_code, 200)

    def test_body_size_limit(self):
        r = self.c.post("/api/input/validate", content=b"x" * (self.main.MAX_BODY_BYTES + 10), headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_rate_limit_is_bounded_and_labelled(self):
        old = self.main.RATE_LIMIT_LLM_PER_MIN
        try:
            self.main.RATE_LIMIT_LLM_PER_MIN = 3
            codes = [self.c.post("/api/copilot", json={"query": "hi", "clinical_text": ""}).status_code for _ in range(5)]
            self.assertIn(429, codes)
            r = self.c.post("/api/copilot", json={"query": "hi"})
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.json()["detail"]["status"], "rate_limited")
            self.assertIn("retry-after", {k.lower() for k in r.headers})
        finally:
            self.main.RATE_LIMIT_LLM_PER_MIN = old

    def test_unhandled_errors_are_generic(self):
        orig = self.main.retrieval_pipeline.run
        try:
            def boom(*a, **k):
                raise RuntimeError("SECRET-PATIENT-TEXT sk-should-not-leak")
            self.main.retrieval_pipeline.run = boom
            r = self.c.post("/api/retrieve", json={"clinical_text": TEXT})
            self.assertEqual(r.status_code, 500)
            self.assertNotIn("SECRET-PATIENT-TEXT", r.text)
            self.assertNotIn("Traceback", r.text)
        finally:
            self.main.retrieval_pipeline.run = orig

    def test_schema_validation_rejects_wrong_types(self):
        self.assertEqual(self.c.post("/api/rank", json={"clinical_text": ["a"], "top_k": "many"}).status_code, 422)

    def test_security_headers_and_no_store(self):
        r = self.c.get("/")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        self.assertEqual(r.headers.get("referrer-policy"), "no-referrer")

    def test_api_docs_are_disabled_in_production_mode(self):
        src = open("src/api/main.py", encoding="utf-8").read()
        self.assertIn('None if PRODUCTION else "/docs"', src)
        self.assertIn('None if PRODUCTION else "/openapi.json"', src)


class TestFrontendCredentialHandling(unittest.TestCase):
    """Static checks of the browser client: bearer credentials attached consistently, never in URLs, no secrets bundled."""

    @staticmethod
    def read(p):
        with open(p, encoding="utf-8") as f:
            return f.read()

    def test_every_api_call_goes_through_the_authenticated_fetch(self):
        import re
        src = self.read("frontend/src/api/client.js")
        raw = [m.group(0) for m in re.finditer(r"await fetch\(", src)]
        self.assertEqual(len(raw), 1, "only the authFetch wrapper may call fetch() directly")
        self.assertIn("Authorization", src)
        self.assertNotIn("X-Case-Token", src)
        self.assertNotIn("localStorage", src)                       # session token lives in sessionStorage (per tab), never localStorage
        self.assertIn("sessionStorage", src)
        self.assertIn("import.meta.env.VITE_API_BASE_URL", src)
        self.assertNotRegex(src, r"\?(token|access_token)=")        # credentials never travel in URLs

    def test_session_expiry_is_surfaced_without_discarding_unsaved_work(self):
        src = self.read("frontend/src/api/client.js")
        for needle in ("rd-auth-expired", "401"):
            self.assertIn(needle, src)
        ctx = self.read("frontend/src/components/AuthContext.jsx")
        app = self.read("frontend/src/App.jsx")
        self.assertIn("rd-auth-expired", ctx)
        self.assertIn("Session expired", app)
        self.assertIn("{children}", app)                           # the page stays mounted underneath the sign-in overlay

    def test_login_registration_logout_ui_exists(self):
        self.assertTrue(os.path.exists("frontend/src/components/AuthPanel.jsx"))
        nav = self.read("frontend/src/components/Navbar.jsx")
        self.assertIn("Log out", nav)
        self.assertIn("Log out", self.read("frontend/src/app/TopBar.jsx"))     # account menu of the internal app shell


class TestSecretHygiene(unittest.TestCase):
    def test_no_secrets_in_repo_or_bundle(self):
        key = os.environ.get("GROQ_API_KEY", "")
        for root in ("src", "configs", "reports", "frontend/src", "frontend/dist", "README.md", ".env.example", "migrations", "docs", "docker-compose.yml"):
            if not os.path.exists(root):
                continue
            paths = [root] if os.path.isfile(root) else [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]
            for p in paths:
                if p.endswith((".pyc", ".png", ".webp", ".jpg", ".pdf", ".parquet", ".npy", ".faiss", ".pkl")):
                    continue
                t = open(p, encoding="utf-8", errors="ignore").read()
                self.assertNotRegex(t, r"gsk_[A-Za-z0-9]{20,}", p)
                if key:
                    self.assertNotIn(key, t, p)
        env_example = open(".env.example", encoding="utf-8").read()
        self.assertEqual(env_example.count("GROQ_API_KEY="), 1)
        for line in env_example.splitlines():                       # no value is committed for any credential
            if line.startswith(("GROQ_API_KEY=", "DATABASE_URL=", "POSTGRES_PASSWORD=")):
                self.assertEqual(line.split("=", 1)[1].strip(), "", line)

    def test_gitignore_protects_env_and_runtime_data(self):
        g = open(".gitignore", encoding="utf-8").read()
        for needle in (".env", "data/drafts/", "data/app.db"):
            self.assertIn(needle, g)


if __name__ == "__main__":
    unittest.main()
