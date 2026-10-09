"""Doctor Copilot final repair: Groq 429 handling (fail fast on long waits, precise reason, retry metadata) and API-level guards.
All tests here are MOCKED (no Groq call) except TestLiveCopilot, which is skipped unless a real request succeeds."""
import io
import json
import os
import sys
import time
import unittest
import urllib.error
from email.message import Message
from unittest import mock

import yaml

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()
from src.input_guard.groq_provider import GroqClient, ProviderRateLimited  # noqa: E402

TPD_BODY = json.dumps({"error": {"message": "Rate limit reached for model `m` in organization `org_x` service tier `on_demand` on tokens per "
                                            "day (TPD): Limit 200000, Used 199000, Requested 2900. Please try again in 8m9s.",
                                 "type": "tokens", "code": "rate_limit_exceeded"}}).encode()


def http_error(code, body=b"{}", retry_after=None):
    h = Message()
    if retry_after is not None:
        h["retry-after"] = str(retry_after)
    return urllib.error.HTTPError("https://api.groq.com/x", code, "err", h, io.BytesIO(body))


def ok_response(content):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
    return R()


class TestProvider429(unittest.TestCase):
    def client(self):
        return GroqClient(api_key="test-key-not-real", model="openai/gpt-oss-120b", timeout=5, max_retries=2, max_retry_wait=30)

    def test_daily_quota_fails_fast_without_retry(self):
        c = self.client()
        calls = []

        def req(*a, **k):
            calls.append(1)
            raise http_error(429, TPD_BODY, retry_after=490)
        with mock.patch.object(c, "_request", side_effect=req), mock.patch("time.sleep") as sl:
            t = time.time()
            with self.assertRaises(ProviderRateLimited) as cm:
                c.chat_json("sys", "user")
        self.assertEqual(len(calls), 1)                 # no re-send: it would only burn quota
        sl.assert_not_called()
        self.assertLess(time.time() - t, 2)
        e = cm.exception
        self.assertEqual(e.retry_after, 490)
        self.assertEqual(e.limit, "tokens per day (TPD)")
        self.assertIn("about 8 minute", str(e))
        self.assertNotIn("org_x", str(e))               # the organisation id from the body is not echoed

    def test_short_wait_is_retried_then_succeeds(self):
        c = self.client()
        seq = [http_error(429, b'{"error":{"message":"on requests per minute (RPM)"}}', retry_after=2), ok_response({"a": 1})]

        def req(*a, **k):
            x = seq.pop(0)
            if isinstance(x, Exception):
                raise x
            return x
        with mock.patch.object(c, "_request", side_effect=req), mock.patch("time.sleep") as sl:
            self.assertEqual(c.chat_json("sys", "user"), {"a": 1})
        sl.assert_called_once()
        self.assertLessEqual(sl.call_args[0][0], 2)

    def test_429_without_headers_still_bounded(self):
        c = self.client()
        with mock.patch.object(c, "_request", side_effect=lambda *a, **k: (_ for _ in ()).throw(http_error(429))), mock.patch("time.sleep"):
            with self.assertRaises(ProviderRateLimited):
                c.chat_json("sys", "user")
        self.assertEqual(c.calls, 3)                    # max_retries=2 -> at most 3 sends


class TestCopilotRateLimitFallback(unittest.TestCase):
    def test_fallback_carries_retry_metadata_and_is_labelled(self):
        from src.reasoning.copilot import DoctorCopilot
        cfg = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))
        prov = mock.Mock()
        prov.model = "openai/gpt-oss-120b"
        prov.check_health.return_value = {"status": "healthy"}
        prov.generate_json_with_meta.side_effect = ProviderRateLimited("limit (HTTP 429, tokens per day (TPD)). Try again in about 8 minute(s).",
                                                                       retry_after=490, limit="tokens per day (TPD)")
        cp = DoctorCopilot(cfg, provider=prov)
        packet = {"candidate_id": "D:1", "disease_name": "Disease one", "rank": 1,
                  "evidence": [{"id": "C1-E1", "type": "phenotype_match", "text": "Seizure matches.", "source": "HPO"}]}
        r = cp.answer_query("Why is the top candidate ranked first?", {"clinical_text": "Synthetic.", "fused_candidates": [{"packet": packet}]})
        self.assertTrue(r["fallback"])
        self.assertEqual(r["generated_by"], "deterministic_fallback")
        self.assertTrue(r["answer"].startswith("Deterministic fallback (no language model was used)"))
        self.assertEqual(r["provider"]["status"], "rate_limited")
        self.assertTrue(r["provider"]["retryable"])
        self.assertEqual(r["provider"]["retry_after_seconds"], 490)
        self.assertEqual(r["provider"]["limit"], "tokens per day (TPD)")
        self.assertEqual(prov.generate_json_with_meta.call_count, 1)


class TestCopilotApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from src.api import main
        cls.main = main
        cls._ctx = TestClient(main.app, raise_server_exceptions=False)
        cls.c = cls._ctx.__enter__()
        if main.retrieval_pipeline is None:
            raise unittest.SkipTest("pipeline not loaded")
        authed_client(cls.c)
        r = cls.c.post("/api/diagnose", json={"clinical_text": "Synthetic case. Hypotonia, short stature and recurrent seizures.", "top_k": 5})
        assert r.status_code == 200, r.text
        cls.case_id = r.json()["case_id"]

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main._hits.clear()

    def test_empty_query(self):
        self.assertEqual(self.c.post("/api/copilot", json={"query": "   ", "case_id": self.case_id}).status_code, 400)
        self.assertEqual(self.c.post("/api/copilot", json={}).status_code, 422)

    def test_requires_session(self):
        from fastapi.testclient import TestClient
        anon = TestClient(self.main.app, raise_server_exceptions=False)
        self.assertEqual(anon.post("/api/copilot", json={"query": "Why?", "case_id": self.case_id}).status_code, 401)
        bad = TestClient(self.main.app, raise_server_exceptions=False)
        bad.headers.update({"Authorization": "Bearer not-a-real-session"})
        self.assertEqual(bad.post("/api/copilot", json={"query": "Why?", "case_id": self.case_id}).status_code, 401)

    def test_foreign_case_does_not_leak(self):
        from fastapi.testclient import TestClient
        other = TestClient(self.main.app, raise_server_exceptions=False)
        authed_client(other)
        with mock.patch.object(self.main.doctor_copilot.provider, "check_health", return_value={"status": "offline"}):
            r = other.post("/api/copilot", json={"query": "Which phenotypes match the top candidate?", "case_id": self.case_id})
        self.assertEqual(r.status_code, 200)
        body = json.dumps(r.json()).lower()
        self.assertNotIn("hypotonia", body)              # the other user's case text and findings are never used
        self.assertEqual(r.json()["referenced_candidates"], [])

    def test_owner_rate_limited_fallback_through_api(self):
        prov = self.main.doctor_copilot.provider
        with mock.patch.object(prov, "check_health", return_value={"status": "healthy"}), \
             mock.patch.object(prov, "generate_json_with_meta", side_effect=ProviderRateLimited("limit", retry_after=300, limit="tokens per day (TPD)")):
            r = self.c.post("/api/copilot", json={"query": "Why is the top candidate ranked first?", "case_id": self.case_id}).json()
        self.assertTrue(r["fallback"])
        self.assertEqual(r["provider"]["retry_after_seconds"], 300)
        self.assertTrue(r["patient_record_findings"])     # patient findings come from the owner's own case


class TestCopilotFrontend(unittest.TestCase):
    def test_states(self):
        ui = open("frontend/src/components/DoctorCopilot.jsx", encoding="utf-8").read()
        for s in ("Retry this question", "retry_after_seconds", "DETERMINISTIC FALLBACK", "err.httpStatus === 401", "isLoading"):
            self.assertIn(s, ui)
        self.assertNotIn("The access token for this case is missing", ui)
        cl = open("frontend/src/api/client.js", encoding="utf-8").read()
        i = cl.index("export async function askDoctorCopilot")
        self.assertIn("err.httpStatus = res.status", cl[i:i + 700])


if __name__ == "__main__":
    unittest.main()
