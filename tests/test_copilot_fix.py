"""Doctor Copilot regression tests. Providers are FIXTURES (scripted stand-ins, not Groq); evidence packets are a saved real pipeline output.
The live Groq request is exercised by scripts/copilot_repro.py and recorded in the fix report."""
import copy
import json
import os
import sys
import unittest

sys.path.append(os.path.abspath("."))
import yaml

from src.input_guard.groq_provider import InvalidModelOutput, ProviderRateLimited, ProviderTimeout
from src.reasoning.copilot import DoctorCopilot
from src.reasoning.grounding import Claim, check_claim

FX = json.load(open("tests/fixtures/phase4r_case.json", encoding="utf-8"))
CFG = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))


def ctx():
    return {"clinical_text": FX["clinical_text"], "fused_candidates": copy.deepcopy(FX["fused_candidates"]),
            "hpo_terms": [{"hpo_id": "HP:0001252", "name": "Hypotonia"}]}


class Fixture:
    model = "fixture/model"

    def __init__(self, script, health="healthy"):
        self.script, self.health, self.calls, self.last = list(script), health, 0, None

    def check_health(self):
        return {"status": self.health}

    def generate_json_with_meta(self, prompt, system_prompt=""):
        self.calls += 1
        self.last_prompt = prompt
        item = self.script.pop(0) if self.script else self.last
        self.last = item
        if isinstance(item, Exception):
            raise item
        return item, {}


def good(**over):
    a = {"answer": "The leading candidate has the highest final score (0.5618) (C1-E12).", "answer_evidence_ids": ["C1-E12"],
         "evidence_points": [{"candidate_id": "ORPHA:1861", "text": "Matches seizures (C1-E2).", "evidence_ids": ["C1-E2"]}],
         "referenced_candidates": [], "cannot_answer_from_evidence": False, "missing_evidence": []}
    a.update(over)
    return a


def ask(script, q="Why was this disease candidate prioritized first?", **kw):
    p = Fixture(script, **kw)
    cp = DoctorCopilot(CFG, provider=p)
    return cp.answer_query(q, ctx()), p


class TestCopilot(unittest.TestCase):
    def test_successful_grounded_answer(self):
        r, _ = ask([good()])
        self.assertEqual(r["generated_by"], "language_model")
        self.assertFalse(r["fallback"])
        self.assertEqual(r["failure_category"], "none")
        self.assertTrue(r["request_id"])
        self.assertEqual(r["evidence_points"][0]["candidate_id"], "ORPHA:1861")

    def test_screenshot_scenario_bare_refusal_is_not_shown(self):
        refusal = good(answer="I'm sorry, I cannot provide an answer to that question based on the available evidence.", answer_evidence_ids=[],
                       evidence_points=[], cannot_answer_from_evidence=True)
        r, p = ask([refusal, refusal])
        self.assertNotIn("I'm sorry", r["answer"])
        self.assertEqual(p.calls, 2)                                  # one corrective retry, bounded
        self.assertEqual(r["failure_category"], "model_refusal")
        self.assertTrue(r["evidence_points"])                         # informative evidence is still returned
        self.assertTrue(r["fallback"] and r["generated_by"] == "evidence_summary")
        self.assertTrue(r["provider"]["retryable"])

    def test_refusal_then_good_answer_on_retry(self):
        r, p = ask([good(answer="I cannot provide an answer.", cannot_answer_from_evidence=True), good()])
        self.assertEqual(r["generated_by"], "language_model")
        self.assertIn("refused", p.last_prompt)

    def test_genuine_insufficient_evidence_is_specific(self):
        a = good(answer="The record shows no blood-pressure data; the recorded evidence shows only phenotype matches (C1-E2).", answer_evidence_ids=["C1-E2"],
                 cannot_answer_from_evidence=True, missing_evidence=["blood pressure measurement"], evidence_points=[])
        r, _ = ask([a], q="What is the patient's blood pressure?")
        self.assertEqual(r["generated_by"], "language_model")
        self.assertEqual(r["missing_evidence"], ["blood pressure measurement"])

    def test_candidate_specific_citations(self):
        cross = good(evidence_points=[{"candidate_id": "ORPHA:1861", "text": "Matches seizures (C2-E2).", "evidence_ids": ["C2-E2"]},
                                      {"candidate_id": "ORPHA:1442", "text": "Matches seizures (C2-E2).", "evidence_ids": ["C2-E2"]}])
        r, _ = ask([cross])
        kept = {(k["candidate_id"], tuple(k["evidence_ids"])) for k in r["evidence_points"]}
        self.assertNotIn(("ORPHA:1861", ("C2-E2",)), kept)            # candidate 1 may not cite candidate 2's evidence
        self.assertIn(("ORPHA:1442", ("C2-E2",)), kept)
        self.assertEqual(r["provider"]["grounding"]["points_removed"], 1)

    def test_unknown_candidate_point_rejected(self):
        r, _ = ask([good(evidence_points=[{"candidate_id": "NOPE:1", "text": "x (C1-E2).", "evidence_ids": ["C1-E2"]}])])
        self.assertEqual(r["evidence_points"], [])

    def test_unsupported_claims_rejected(self):
        for bad in ("Confirmed diagnosis see PMID 12345678 (C1-E12).", "A high score (0.5618) (C1-E12).", "Gene ZZZ9 is involved (C1-E12).",
                    "Sequencing is recommended (C1-E12).", "Take 50 mg (C1-E12)."):
            r, _ = ask([good(answer=bad, answer_evidence_ids=["C1-E12"])] * 2)
            self.assertTrue(r["fallback"], bad)
            self.assertNotIn(bad, r["answer"])

    def test_phenotype_distinction_in_prompt_and_response(self):
        r, p = ask([good()], q="What important distinguishing phenotype is missing?")
        self.assertIn("DISEASE ANNOTATION (not stated for this patient)", p.last_prompt)
        self.assertIn("PATIENT FINDING", p.last_prompt)
        self.assertTrue(r["candidate_annotations_not_in_record"])
        for a in r["candidate_annotations_not_in_record"]:
            self.assertEqual(a["kind"], "candidate_disease_annotation_not_patient_finding")
        self.assertEqual(r["patient_record_findings"][0]["kind"], "patient_record_finding")
        # annotations are only attached when the question is about phenotypes
        r2, _ = ask([good()], q="Why was this disease candidate prioritized first?")
        self.assertEqual(r2["candidate_annotations_not_in_record"], [])

    def test_highest_final_score_only_for_rank_one(self):
        pk = {"rank": 2, "evidence": [{"id": "C2-E12", "text": "score 0.5581", "data": {}}], "genes": []}
        self.assertNotEqual(check_claim(Claim(text="the highest final score (0.5581)", evidence_ids=["C2-E12"]), pk), "")
        pk1 = {"rank": 1, "evidence": [{"id": "C1-E12", "text": "score 0.5618", "data": {}}], "genes": []}
        self.assertEqual(check_claim(Claim(text="the highest final score (0.5618)", evidence_ids=["C1-E12"]), pk1), "")

    def test_provider_failures_are_labelled_and_retryable(self):
        for exc, status in ((ProviderRateLimited("429"), "rate_limited"), (ProviderTimeout("t"), "timeout")):
            r, p = ask([exc])
            self.assertEqual(r["provider"]["status"], status)
            self.assertTrue(r["fallback"] and r["provider"]["retryable"])
            self.assertEqual(r["generated_by"], "deterministic_fallback")
            self.assertEqual(p.calls, 1)                              # no repeated expensive requests on provider failure
            self.assertTrue(r["evidence_points"])

    def test_not_configured_fallback(self):
        r, p = ask([good()], health="not_configured")
        self.assertEqual(r["provider"]["status"], "not_configured")
        self.assertEqual(p.calls, 0)

    def test_malformed_response(self):
        r, p = ask([InvalidModelOutput("bad json")])
        self.assertEqual(r["provider"]["status"], "invalid_output")
        self.assertEqual(r["failure_category"], "malformed_output")
        self.assertEqual(p.calls, 2)
        r2, _ = ask([{"nonsense": 1}])
        self.assertEqual(r2["failure_category"], "schema_error")

    def test_scope_limited_question_makes_no_llm_call_and_gives_no_advice(self):
        r, p = ask([good()], q="What genetic and confirmatory molecular tests are indicated?")
        self.assertEqual(p.calls, 0)
        self.assertEqual(r["generated_by"], "evidence_summary")
        self.assertFalse(r["fallback"])
        self.assertIn("does not recommend tests", r["answer"])
        self.assertNotIn("is indicated", r["answer"])

    def test_no_case_context(self):
        p = Fixture([good()])
        r = DoctorCopilot(CFG, provider=p).answer_query("Why?", {"fused_candidates": []})
        self.assertEqual(r["provider"]["status"], "no_case_context")
        self.assertEqual(p.calls, 0)

    def test_no_patient_text_or_prompt_in_logs(self):
        with self.assertLogs("src.reasoning.copilot", level="INFO") as cm:
            ask([good()])
        out = "\n".join(cm.output)
        self.assertNotIn("hypotonia", out.lower())
        self.assertIn("req=", out)


class TestSmallTalk(unittest.TestCase):
    def test_greeting_makes_no_llm_call(self):
        for q in ("hi", "Hello!", "thanks", "x"):
            r, p = ask([good()], q=q)
            self.assertEqual(p.calls, 0, q)
            self.assertEqual(r["generated_by"], "assistant_notice")
            self.assertFalse(r["fallback"])
            self.assertEqual(r["evidence_points"], [])


class TestVoiceUi(unittest.TestCase):
    def test_voice_controls_present(self):
        v = open("frontend/src/components/DoctorCopilot.jsx", encoding="utf-8").read()
        for needle in ("SpeechRecognition", "speechSynthesis", "Start voice input", "Read aloud", "Send automatically after dictation",
                       "microphone permission was denied".capitalize()[:20], "not supported in this browser", "ASSISTANT NOTICE"):
            self.assertIn(needle, v)
        self.assertNotRegex(v.lower(), r"fetch\(|groq|openai|whisper")      # voice stays in the browser: no new provider or network call


class TestUnicodeHyphen(unittest.TestCase):
    def test_unicode_hyphen_ids_are_normalised(self):
        from src.input_guard.groq_provider import GroqClient
        body = {"choices": [{"message": {"content": json.dumps({"answer": "Matches (C1‑E12) and C1–E2"})}}]}
        out = GroqClient._parse(body)
        self.assertEqual(out["answer"], "Matches (C1-E12) and C1-E2")
        r, _ = ask([good(answer="The first candidate has the highest final score (0.5618) (C1-E12).")])
        self.assertEqual(r["generated_by"], "language_model")


class TestCopilotFrontend(unittest.TestCase):
    @staticmethod
    def read():
        with open("frontend/src/components/DoctorCopilot.jsx", encoding="utf-8") as f:
            return f.read()

    def test_renders_success_and_fallback_states(self):
        v = self.read()
        for needle in ("AI-generated from the recorded evidence", "DETERMINISTIC FALLBACK", "EVIDENCE SUMMARY", "Retry this question",
                       "Evidence not available", "NOT findings in this patient", "Patient-record findings used", "failureCategory"):
            self.assertIn(needle, v)
        self.assertNotIn("I'm sorry", v)
        self.assertNotRegex(v.lower(), r"groq|ollama")


if __name__ == "__main__":
    unittest.main()
