"""Groq provider + migrated route tests (Phase 5R.2).

MOCKED: everything in TestGroqClientMocked / TestRoutesMockedProvider (HTTP is patched or a FIXTURE provider is injected).
LIVE:   TestLiveGroq (real network, real key; skipped if GROQ_API_KEY is unset). Live tests are the only ones that prove Groq works.
"""
import copy
import io
import json
import logging
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.append(os.path.abspath("."))
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()

import yaml  # noqa: E402

from src.input_guard import groq_provider as gp  # noqa: E402
from src.input_guard.groq_provider import (GroqClient, InvalidModelOutput, ProviderAuthError, ProviderModelError, ProviderNotConfigured,  # noqa: E402
                                           ProviderRateLimited, ProviderTimeout, ProviderUnavailable)

SECRET = "gsk_FIXTURE_SECRET_VALUE_1234567890"
CFG = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))


class FakeResp(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def completion(content):
    return {"choices": [{"message": {"content": content}}]}


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(b"{}"))


def client(**kw):
    kw.setdefault("api_key", SECRET)
    kw.setdefault("model", "test/model")
    kw.setdefault("max_retry_wait", 0.0)
    return GroqClient(**kw)


class TestGroqClientMocked(unittest.TestCase):
    def patch(self, side_effect):
        return mock.patch.object(gp.urllib.request, "urlopen", side_effect=side_effect)

    def test_success(self):
        with self.patch([FakeResp(completion('{"ok": true}'))]) as m:
            self.assertEqual(client().chat_json("s", "u"), {"ok": True})
            sent = m.call_args[0][0]
            self.assertEqual(sent.get_header("Authorization"), "Bearer " + SECRET)       # key only in the header, server-side
            self.assertNotIn(SECRET, sent.data.decode())

    def test_missing_key(self):
        with self.assertRaises(ProviderNotConfigured):
            client(api_key="").chat_json("s", "u")
        self.assertEqual(client(api_key="").check_health()["status"], "not_configured")

    def test_invalid_key_no_retry(self):
        with self.patch([http_error(401)]) as m:
            with self.assertRaises(ProviderAuthError) as cm:
                client().chat_json("s", "u")
            self.assertEqual(m.call_count, 1)
            self.assertEqual(cm.exception.status, "auth_error")

    def test_invalid_model(self):
        with self.patch([http_error(404)]):
            with self.assertRaises(ProviderModelError) as cm:
                client().chat_json("s", "u")
            self.assertEqual(cm.exception.status, "model_unavailable")

    def test_timeout_is_retried_then_reported(self):
        with self.patch(TimeoutError("timed out")) as m:
            with self.assertRaises(ProviderTimeout):
                client(max_retries=2).chat_json("s", "u")
            self.assertEqual(m.call_count, 3)

    def test_rate_limit_retry_limit(self):
        with self.patch(http_error(429, {"retry-after": "0"})) as m:
            with self.assertRaises(ProviderRateLimited) as cm:
                client(max_retries=2).chat_json("s", "u")
            self.assertEqual(m.call_count, 3)                                              # bounded: 1 + 2 retries
            self.assertEqual(cm.exception.status, "rate_limited")

    def test_rate_limit_then_success(self):
        with self.patch([http_error(429, {"retry-after": "0"}), FakeResp(completion('{"a": 1}'))]):
            self.assertEqual(client().chat_json("s", "u"), {"a": 1})

    def test_server_error(self):
        with self.patch(http_error(503)) as m:
            with self.assertRaises(ProviderUnavailable) as cm:
                client(max_retries=1).chat_json("s", "u")
            self.assertEqual(m.call_count, 2)
            self.assertEqual(cm.exception.status, "provider_unavailable")

    def test_malformed_outputs(self):
        for body in (completion("not json at all"), completion(""), {"choices": []}, completion("[1, 2]"), {"unexpected": True}):
            with self.patch([FakeResp(body)]):
                with self.assertRaises(InvalidModelOutput):
                    client().chat_json("s", "u")

    def test_json_wrapped_in_text_is_recovered(self):
        with self.patch([FakeResp(completion('Here you go: {"a": 2} thanks'))]):
            self.assertEqual(client().chat_json("s", "u"), {"a": 2})

    def test_strict_schema_falls_back_to_json_mode_on_400(self):
        with self.patch([http_error(400), FakeResp(completion('{"a": 3}'))]) as m:
            self.assertEqual(client().chat_json("s", "u", schema={"type": "object"}), {"a": 3})
            self.assertEqual(json.loads(m.call_args[0][0].data)["response_format"], {"type": "json_object"})

    def test_total_time_budget(self):
        with self.patch(TimeoutError("timed out")):
            with self.assertRaises(ProviderTimeout):
                client(max_retries=5, total_timeout=0.5).chat_json("s", "u")

    def test_secret_never_in_errors_or_logs(self):
        with self.assertLogs(level="DEBUG") as logs, self.patch(http_error(429, {"retry-after": "0"})):
            try:
                client(max_retries=1).chat_json("PROMPT-TEXT-MARKER", "u")
            except Exception as e:     # noqa: BLE001
                self.assertNotIn(SECRET, str(e))
            logging.getLogger("x").debug("anchor")
        self.assertNotIn(SECRET, "\n".join(logs.output))
        self.assertNotIn("PROMPT-TEXT-MARKER", "\n".join(logs.output))

    def test_health_states(self):
        with self.patch([FakeResp({"data": [{"id": "test/model"}]})]):
            self.assertEqual(client().check_health(use_cache=False)["status"], "healthy")
        with self.patch([FakeResp({"data": [{"id": "other"}]})]):
            self.assertEqual(client().check_health(use_cache=False)["status"], "model_missing")
        with self.patch([http_error(401)]):
            self.assertEqual(client().check_health(use_cache=False)["status"], "auth_error")
        with self.patch(urllib.error.URLError("down")):
            self.assertEqual(client().check_health(use_cache=False)["status"], "offline")

    def test_model_resolution_single_source(self):
        self.assertEqual(gp.resolve_model({"llm": {"model": "cfg/model"}}) if "GROQ_MODEL" not in os.environ else "cfg/model", "cfg/model")
        with mock.patch.dict(os.environ, {"GROQ_MODEL": "env/model"}):
            self.assertEqual(gp.resolve_model({"llm": {"model": "cfg/model"}}), "env/model")
        self.assertNotIn("compound-mini", json.dumps(CFG))


class TestEnhancementGuard(unittest.TestCase):
    def guard(self, groq_payload, status="ok"):
        from src.input_guard.input_validator import InputValidatorGuard
        g = InputValidatorGuard(groq_api_key=SECRET, groq_model="test/model")
        g.groq_provider.enhance_detailed = lambda text: (groq_payload, status)
        return g

    TEXT = "pt has dev delay and seizures since 2 yrs"

    def test_quality_gate_runs_before_llm(self):
        g = self.guard({"status": "NEEDS_ENHANCEMENT", "enhanced_text": "x"})
        g.groq_provider.enhance_detailed = mock.Mock(side_effect=AssertionError("LLM must not be called"))
        r = g.enhance_text("asdfgh")
        self.assertIn(r.status, ("NON_CLINICAL", "INAPPROPRIATE", "INSUFFICIENT"))

    def test_statuses_for_failures(self):
        for call_status, expected in (("not_configured", "ENHANCEMENT_UNAVAILABLE"), ("auth_error", "ENHANCEMENT_UNAVAILABLE"), ("rate_limited", "ENHANCEMENT_RATE_LIMITED"),
                                      ("timeout", "ENHANCEMENT_TIMEOUT"), ("invalid_output", "ENHANCEMENT_MALFORMED")):
            r = self.guard(None, call_status).enhance_text(self.TEXT)
            self.assertEqual(r.status, expected, call_status)
            self.assertEqual(r.enhanced_text, self.TEXT)                      # original text kept
            self.assertNotIn(SECRET, r.model_dump_json())

    def test_rewrite_with_new_number_rejected(self):
        r = self.guard({"status": "NEEDS_ENHANCEMENT", "enhanced_text": "Patient has developmental delay and seizures since 5 years.", "changes": ["x"]}).enhance_text(self.TEXT)
        self.assertEqual(r.status, "ENHANCEMENT_REJECTED")
        self.assertEqual(r.enhanced_text, self.TEXT)

    def test_rewrite_dropping_negation_rejected(self):
        r = self.guard({"status": "NEEDS_ENHANCEMENT", "enhanced_text": "Patient has seizures.", "changes": ["x"]}).enhance_text("pt has no seizures")
        self.assertEqual(r.status, "ENHANCEMENT_REJECTED")

    def test_faithful_rewrite_accepted(self):
        r = self.guard({"status": "NEEDS_ENHANCEMENT", "enhanced_text": "Patient has developmental delay and seizures since 2 years.", "changes": ["expanded"]}).enhance_text(self.TEXT)
        self.assertEqual(r.status, "NEEDS_ENHANCEMENT")


# ----------------------------------------------------------------------------------------------------------------------------
class FixtureProvider:
    """FIXTURE: a language-model stand-in injected into the real app to test the route logic (not Groq)."""
    model = "fixture/model"

    def __init__(self, behaviour="ok", health="healthy"):
        self.behaviour, self.health, self.calls = behaviour, health, 0

    def check_health(self):
        return {"status": self.health, "model": self.model}

    def generate_json_with_meta(self, prompt, system_prompt=""):
        self.calls += 1
        b = self.behaviour
        if isinstance(b, Exception):
            raise b
        return b(prompt), {"latency_ms": 1.0}

    generate_json = lambda self, p, s="": self.generate_json_with_meta(p, s)[0]    # noqa: E731


def fixture_answer(prompt):
    import re
    cands = re.findall(r'candidate_id="([^"]+)" name="[^"]*" rank=(\d+)', prompt)
    return {"candidates": [{"candidate_id": cid, "summary": f"Retrieved with a retrieval score (C{r}-E1).", "ranking_note": f"Rank {r} (C{r}-E1).", "uncertainties": []}
                           for cid, r in cands]}


def copilot_answer(prompt):
    return {"answer": "Retrieved by similarity (C1-E1).", "answer_evidence_ids": ["C1-E1"], "evidence_points": [{"candidate_id": "ORPHA:1861", "text": "Retrieval was used (C1-E1).", "evidence_ids": ["C1-E1"]}],
            "referenced_candidates": [], "cannot_answer_from_evidence": False}


class TestRoutesMockedProvider(unittest.TestCase):
    """Real pipeline (NER/HPO/FAISS/ranking/fusion) with a FIXTURE language-model provider injected."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from src.api import main
        cls.main = main
        cls._ctx = TestClient(main.app)
        cls.client = cls._ctx.__enter__()
        authed_client(cls.client)
        cls.text = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
        cls.orig = (main.llm_reasoner.provider, main.doctor_copilot.provider)

    @classmethod
    def tearDownClass(cls):
        cls.main.llm_reasoner.provider, cls.main.doctor_copilot.provider = cls.orig
        cls._ctx.__exit__(None, None, None)

    def setUp(self):
        self.main.llm_reasoner.cache.clear()
        d = self.client.post("/api/diagnose", json={"clinical_text": self.text, "top_k": 5}).json()
        self.case_id, self.diag = d["case_id"], d

    def use(self, p):
        self.main.llm_reasoner.provider = p
        self.main.doctor_copilot.provider = p
        return p

    def test_diagnose_default_does_not_call_llm(self):
        p = self.use(FixtureProvider(fixture_answer))
        self.client.post("/api/diagnose", json={"clinical_text": self.text, "top_k": 5})
        self.assertEqual(p.calls, 0)
        self.assertEqual(self.diag["reasoning"]["provider"]["status"], "not_requested")

    def test_diagnose_explain_true(self):
        self.use(FixtureProvider(fixture_answer))
        d = self.client.post("/api/diagnose", json={"clinical_text": self.text, "top_k": 5, "explain": True}).json()
        self.assertEqual(d["reasoning"]["provider"]["status"], "ok")
        self.assertEqual(d["top_explanation"]["generated_by"], "language_model")

    def test_reason_grounded_and_ranking_untouched(self):
        self.use(FixtureProvider(fixture_answer))
        r = self.client.post("/api/reason", json={"case_id": self.case_id}).json()["reasoning"]
        self.assertEqual(r["provider"]["status"], "ok")
        self.assertFalse(r["provider"]["fallback"])
        self.assertEqual([c["candidate_id"] for c in r["candidates"]], [c["disease_id"] for c in self.diag["fused_candidates"]])
        ids = {e["id"] for c in self.diag["fused_candidates"] for e in c["packet"]["evidence"]}
        for c in r["candidates"]:
            self.assertTrue(all(ref["evidence_id"] in ids for ref in c["source_references"]))
        again = self.client.post("/api/diagnose", json={"clinical_text": self.text, "top_k": 5}).json()
        self.assertEqual([c["final_score"] for c in again["fused_candidates"]], [c["final_score"] for c in self.diag["fused_candidates"]])

    def test_reason_unsupported_claims_removed(self):
        def bad(prompt):
            a = fixture_answer(prompt)
            a["candidates"][0]["summary"] = "Confirmed diagnosis, see PMID 12345678 (C1-E1)."
            a["candidates"][1]["summary"] = "Take 50 mg daily (C2-E1)."
            a["candidates"][2]["summary"] = "Gene ZZZ9 is implicated (C3-E1)."
            return a
        self.use(FixtureProvider(bad))
        r = self.client.post("/api/reason", json={"case_id": self.case_id}).json()["reasoning"]
        blob = json.dumps(r["candidates"])
        for x in ("PMID 12345678", "50 mg", "ZZZ9"):
            self.assertNotIn(x, blob)
        self.assertGreaterEqual(r["provider"]["grounding"]["claims_removed"], 3)

    def test_reason_labelled_fallback_when_unavailable(self):
        for provider, status in ((FixtureProvider(health="not_configured"), "not_configured"), (FixtureProvider(health="offline"), "provider_unavailable"),
                                 (FixtureProvider(gp.ProviderRateLimited("429")), "rate_limited"), (FixtureProvider(ProviderTimeout("t")), "timeout"),
                                 (FixtureProvider(ProviderAuthError("a")), "auth_error")):
            self.main.llm_reasoner.cache.clear()
            self.use(provider)
            r = self.client.post("/api/reason", json={"case_id": self.case_id})
            self.assertEqual(r.status_code, 200)
            reasoning = r.json()["reasoning"]
            self.assertEqual(reasoning["provider"]["status"], status)
            self.assertTrue(reasoning["provider"]["fallback"])
            self.assertTrue(all(c["generated_by"] == "deterministic_fallback" and c["fallback"] for c in reasoning["candidates"]))

    def test_reason_malformed_output_bounded_retries(self):
        p = self.use(FixtureProvider(InvalidModelOutput("bad")))
        r = self.client.post("/api/reason", json={"case_id": self.case_id}).json()["reasoning"]
        self.assertEqual(r["provider"]["status"], "invalid_output")
        self.assertEqual(p.calls, self.main.llm_reasoner.max_attempts)

    def test_explain_route(self):
        self.use(FixtureProvider(fixture_answer))
        r = self.client.post("/api/explain", json={"case_id": self.case_id, "disease_id": self.diag["fused_candidates"][0]["disease_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["candidate_id"], self.diag["fused_candidates"][0]["disease_id"])

    def test_differential_is_deterministic_no_llm(self):
        p = self.use(FixtureProvider(fixture_answer))
        r = self.client.post("/api/differential", json={"case_id": self.case_id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(p.calls, 0)

    def test_copilot_grounded_and_fallback(self):
        self.use(FixtureProvider(copilot_answer))
        r = self.client.post("/api/copilot", json={"query": "Why is the top candidate first?", "case_id": self.case_id}).json()
        self.assertEqual(r["generated_by"], "language_model")
        self.assertFalse(r["fallback"])
        self.use(FixtureProvider(health="not_configured"))
        f = self.client.post("/api/copilot", json={"query": "Why was the top candidate prioritized?", "case_id": self.case_id}).json()
        self.assertTrue(f["fallback"])
        self.assertEqual(f["generated_by"], "deterministic_fallback")
        self.assertEqual(f["provider"]["status"], "not_configured")

    def test_health_has_no_secret_or_ollama(self):
        h = self.client.get("/").text.lower()
        self.assertNotIn("gsk_", h)
        self.assertNotIn("ollama", h)
        self.assertNotIn(os.environ.get("GROQ_API_KEY", "\x00").lower(), h)

    def test_retrieval_and_ranking_work_without_llm(self):
        self.use(FixtureProvider(health="not_configured"))
        r = self.client.post("/api/rank", json={"clinical_text": self.text, "top_k": 5})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ranked_candidates"])


ProviderTimeout = gp.ProviderTimeout
ProviderAuthError = gp.ProviderAuthError


class TestNoOllamaInActiveCode(unittest.TestCase):
    def test_repository_has_no_active_ollama_paths(self):
        bad = []
        for root in ("src", "configs", os.path.join("frontend", "src")):
            for d, _, files in os.walk(root):
                if "__pycache__" in d or "node_modules" in d:
                    continue
                for f in files:
                    if f.endswith((".py", ".yaml", ".yml", ".jsx", ".js", ".json", ".md")):
                        t = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read().lower()
                        if any(w in t for w in ("ollama", "11434", "gemma4", "compound-mini")):
                            bad.append(os.path.join(d, f))
        self.assertEqual(bad, [])
        self.assertNotIn("ollama", open("requirements.txt", encoding="utf-8").read().lower())
        self.assertEqual(CFG["llm"]["provider"], "groq")

    def test_frontend_bundle_has_no_key_or_provider(self):
        for d, _, files in os.walk(os.path.join("frontend", "dist")):
            for f in files:
                t = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read().lower()
                self.assertNotIn("gsk_", t)
                self.assertNotIn("groq_api_key", t)
                self.assertNotIn("ollama", t)

    def test_unsupported_provider_rejected(self):
        from src.reasoning.llm_provider import get_llm_provider
        for name in ("ollama", "openai", "gemini"):
            with self.assertRaises(ValueError):
                get_llm_provider({"llm": {"provider": name}})


@unittest.skipUnless(os.environ.get("GROQ_API_KEY"), "GROQ_API_KEY not set - live tests skipped")
class TestLiveGroq(unittest.TestCase):
    """LIVE network calls with the real configured key and model."""

    @classmethod
    def setUpClass(cls):
        from src.reasoning.llm_provider import get_llm_provider
        cls.provider = get_llm_provider(CFG)

    def test_live_health_lists_configured_model(self):
        self.assertEqual(self.provider.check_health()["status"], "healthy")

    def test_live_completion(self):
        r = self.provider.client.verify_completion()
        self.assertEqual(r["status"], "ok", r)

    def test_live_enhancement_flow(self):
        from src.input_guard.input_validator import InputValidatorGuard
        g = InputValidatorGuard()
        r = g.enhance_text("pt has dev delay and seizures since 2 yrs")
        self.assertIn(r.status, ("NEEDS_ENHANCEMENT", "VALID_CLINICAL", "ENHANCEMENT_REJECTED", "ENHANCEMENT_RATE_LIMITED"), r.status)
        self.assertNotIn(os.environ["GROQ_API_KEY"], r.model_dump_json())

    def test_live_reasoning_end_to_end(self):
        from src.reasoning.llm_reasoner import LLMReasoner
        fx = json.load(open("tests/fixtures/phase4r_case.json", encoding="utf-8"))
        pk = [c["packet"] for c in fx["fused_candidates"]][:2]
        out = LLMReasoner(CFG, provider=self.provider).explain_candidates(fx["clinical_text"], pk)
        self.assertIn(out["provider"]["status"], ("ok", "partial", "rate_limited"), out["provider"])
        if out["provider"]["status"] in ("ok", "partial"):
            self.assertEqual(out["candidates"][0]["generated_by"], "language_model")


if __name__ == "__main__":
    unittest.main()
