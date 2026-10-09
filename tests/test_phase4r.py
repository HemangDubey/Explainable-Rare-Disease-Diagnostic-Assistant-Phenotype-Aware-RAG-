"""Phase 4R tests. Providers here are FIXTURE fakes (clearly labelled); the one live-model test skips if the provider is not healthy."""
import copy
import json
import os
import sys
import unittest

sys.path.append(os.path.abspath("."))
import yaml

from src.reasoning.differential import DifferentialEngine
from src.reasoning.evidence_builder import negated_mentions
from src.reasoning.grounding import Claim, check_claim
from src.reasoning.labels import overlap_label
from src.reasoning.llm_provider import BaseLLMProvider, InvalidModelOutput, ProviderTimeout, ProviderUnavailable
from src.reasoning.llm_reasoner import LLMReasoner

FX = json.load(open("tests/fixtures/phase4r_case.json", encoding="utf-8"))
CFG = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))
TEXT = FX["clinical_text"]


def cands():
    return copy.deepcopy(FX["fused_candidates"])


def packets():
    return [c["packet"] for c in cands()]


class FakeProvider(BaseLLMProvider):
    """FIXTURE provider: not a language model. `script` items are returned/raised in order; the last one repeats."""
    model = "fixture-fake"

    def __init__(self, script, health="healthy"):
        self.script, self.calls, self.health, self.last = list(script), 0, health, None

    def check_health(self):
        return {"status": self.health, "model": self.model}

    def generate_json(self, prompt, system_prompt=""):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.last
        self.last = item
        if isinstance(item, Exception):
            raise item
        return item


def good_answer(pks=None):
    pks = pks or packets()
    return {"candidates": [{"candidate_id": p["candidate_id"], "summary": f"Retrieved with a retrieval score ({p['evidence_ids'][0]}).",
                            "ranking_note": f"See ({p['evidence_ids'][0]}).", "uncertainties": []} for p in pks]}


def reasoner(script, **kw):
    r = LLMReasoner(CFG, provider=FakeProvider(script, **kw))
    r.max_attempts = 2
    return r


class TestGrounding(unittest.TestCase):
    def test_grounded_generation_ok(self):
        out = reasoner([good_answer()]).explain_candidates(TEXT, packets())
        self.assertEqual(out["provider"]["status"], "ok")
        self.assertFalse(out["provider"]["fallback"])
        for c in out["candidates"]:
            self.assertEqual(c["generated_by"], "language_model")
            self.assertIsNone(c["calibrated_confidence"])

    def test_unknown_evidence_id_removed(self):
        bad = good_answer()
        bad["candidates"][0]["summary"] = "Strongly matches (C1-E999)."
        out = reasoner([bad]).explain_candidates(TEXT, packets())
        self.assertNotIn("C1-E999", json.dumps(out["candidates"][0]))

    def test_invalid_claims_rejected(self):
        pk = packets()[0]
        eid = pk["evidence_ids"][0]
        for txt in (f"See PMID 12345678 ({eid}).", f"See https://x.org/a ({eid}).", f"The patient has this disease ({eid}).",
                    f"Start 50 mg daily ({eid}).", f"A high retrieval score ({eid})."):
            self.assertNotEqual(check_claim(Claim(text=txt, evidence_ids=[eid]), pk), "", txt)
        self.assertEqual(check_claim(Claim(text=pk["evidence"][0]["text"], evidence_ids=[eid]), pk), "")

    def test_claim_without_citation_rejected(self):
        self.assertNotEqual(check_claim(Claim(text="Some claim.", evidence_ids=[]), packets()[0]), "")


class TestProviderStates(unittest.TestCase):
    def assert_fallback(self, out, status):
        self.assertEqual(out["provider"]["status"], status)
        self.assertTrue(out["provider"]["fallback"])
        self.assertEqual(len(out["candidates"]), 5)
        for c in out["candidates"]:
            self.assertEqual(c["generated_by"], "deterministic_fallback")
            self.assertTrue(c["fallback"])
            self.assertEqual(c["provider_status"], status)

    def test_offline_is_provider_unavailable(self):
        self.assert_fallback(reasoner([good_answer()], health="offline").explain_candidates(TEXT, packets()), "provider_unavailable")

    def test_model_missing(self):
        self.assert_fallback(reasoner([good_answer()], health="model_missing").explain_candidates(TEXT, packets()), "model_missing")

    def test_timeout_does_not_crash(self):
        self.assert_fallback(reasoner([ProviderTimeout("slow")]).explain_candidates(TEXT, packets()), "timeout")

    def test_connection_error(self):
        self.assert_fallback(reasoner([ProviderUnavailable("down")]).explain_candidates(TEXT, packets()), "provider_unavailable")

    def test_malformed_then_valid_retries(self):
        out = reasoner([InvalidModelOutput("not json"), good_answer()]).explain_candidates(TEXT, packets())
        self.assertEqual(out["provider"]["status"], "ok")
        self.assertEqual(out["provider"]["attempts"], 2)

    def test_malformed_twice_is_invalid_output(self):
        r = reasoner([InvalidModelOutput("x"), {"unexpected": 1}])
        self.assert_fallback(r.explain_candidates(TEXT, packets()), "invalid_output")
        self.assertEqual(r.provider.calls, 2)  # bounded retries

    def test_fallback_text_is_verbatim_evidence(self):
        out = reasoner([ProviderTimeout("x")]).explain_candidates(TEXT, packets())
        texts = {e["text"] for p in packets() for e in p["evidence"]}
        for c in out["candidates"]:
            for key in ("supporting_evidence", "genetic_evidence", "population_evidence", "missing_or_unverified_evidence"):
                for claim in c[key]:
                    self.assertIn(claim["text"], texts)

    def test_no_candidates(self):
        self.assertEqual(reasoner([good_answer()]).explain_candidates(TEXT, [])["provider"]["status"], "no_candidates")


class TestEvidence(unittest.TestCase):
    def test_score_breakdown_matches_backend(self):
        for c in cands():
            sb = c["score_breakdown"]
            self.assertTrue(sb["matches_backend"])
            self.assertAlmostEqual(sb["final_score"], c["final_score"], places=5)
            w = sb["weights"]
            base = w["w_phenotype"] * sb["phenotype_score"] + w["w_retrieval"] * sb["retrieval_score"]
            self.assertAlmostEqual(base, sb["base_score"], places=4)

    def test_population_never_supporting_and_retrieval_not_probability(self):
        for c in cands():
            self.assertNotEqual(c["population_evidence"]["category"], "SUPPORTING")
            self.assertEqual(c["retrieval_evidence"]["label"], "retrieval score (not a probability)")
            self.assertIn("population_contribution", c)

    def test_missing_genes_marked_unavailable(self):
        c = next(c for c in cands() if not c["genes"])
        self.assertIn("gene association", c["evidence_completeness"]["unavailable"])
        self.assertIn("gene_association_unavailable", {e["type"] for e in c["packet"]["evidence"]})
        self.assertLess(c["evidence_completeness"]["fraction"], 1.0)

    def test_unverified_is_not_contradiction(self):
        for c in cands():
            self.assertEqual(c["phenotype_evidence"]["contradicting_phenotypes"], [])
            self.assertTrue(all(e["category"] != "CONTRADICTING" for e in c["evidence_items"]))

    def test_no_negation_without_explicit_negation(self):
        ph = [{"phenotype": "seizures", "start": 12, "end": 20}]
        self.assertEqual(negated_mentions("Patient has seizures.", ph), [])

    def test_label_rules(self):
        self.assertEqual(overlap_label(4, 4, False)["label"], "Strong phenotype overlap")
        self.assertEqual(overlap_label(2, 4, False)["label"], "Partial phenotype overlap")
        self.assertEqual(overlap_label(0, 4, False)["label"], "Insufficient evidence")
        self.assertFalse(overlap_label(4, 4, False)["calibrated"])


class TestDifferential(unittest.TestCase):
    def test_order_scores_and_not_ruled_out(self):
        d = DifferentialEngine(CFG).generate_differential(cands(), TEXT)
        ranks = [t["rank"] for t in d["top_candidates"]]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(len(d["comparisons"]), len(d["top_candidates"]) - 1)
        scores = {c["disease_id"]: c["final_score"] for c in cands()}
        for t in d["top_candidates"]:
            self.assertAlmostEqual(t["final_score"], scores[t["disease_id"]], places=5)
        self.assertNotIn("ruled out by", json.dumps(d).lower())
        self.assertIn("disclaimer", d)

    def test_empty_input(self):
        self.assertEqual(DifferentialEngine(CFG).generate_differential([], TEXT)["top_candidates"], [])


class TestFrontendStates(unittest.TestCase):
    """Static checks that the provider-unavailable / fallback / loading states exist in the JSX."""

    @staticmethod
    def read(p):
        return open(os.path.join("frontend", "src", p), encoding="utf-8").read()

    def test_states_present(self):
        ec, cp = self.read("components/EvidenceCards.jsx"), self.read("components/DoctorCopilot.jsx")
        # the workspace page plus the shared workspace state it uses (reasoning call moved there in the unified-shell redesign)
        dash = self.read("pages/DashboardPage.jsx") + self.read("app/WorkspaceContext.jsx")
        self.assertIn("DETERMINISTIC FALLBACK", ec)
        self.assertIn("Generating a grounded explanation", ec)
        self.assertIn("DETERMINISTIC FALLBACK", cp)
        self.assertIn("reasonCase", dash)
        self.assertIn("Deterministic evidence shown instead", dash)
        self.assertNotIn("AI Reasoning Engine Ready", dash)
        self.assertNotIn("groq", (ec + dash + cp).lower())


class TestLive(unittest.TestCase):
    """LIVE (real Groq call; skipped when the provider is not healthy)."""

    def test_live_model(self):
        from src.reasoning.llm_provider import get_llm_provider
        p = get_llm_provider(CFG)
        h = p.check_health()
        if h.get("status") != "healthy":
            self.skipTest(f"language model not healthy: {h.get('status')}")
        out = LLMReasoner(CFG, provider=p).explain_candidates(TEXT, packets()[:2])
        self.assertIn(out["provider"]["status"], ("ok", "partial", "timeout", "invalid_output", "rate_limited"))
        if out["provider"]["status"] == "ok":
            self.assertEqual(out["candidates"][0]["generated_by"], "language_model")


if __name__ == "__main__":
    unittest.main()
