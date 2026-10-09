"""Phase 3R API tests against the real pipeline. Run: python -m unittest tests.test_phase3r_api -v"""
import os
import sys
import unittest

sys.path.append(os.path.abspath("."))
from fastapi.testclient import TestClient  # noqa: E402
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
STATES = {"available", "not_found", "unavailable", "not_applicable"}


class TestPhase3RApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.api.main import app
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()
        authed_client(cls.client)

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_rank_exposes_structured_population_evidence(self):
        d = self.client.post("/api/rank", json={"clinical_text": TEXT, "top_k": 5}).json()
        self.assertEqual(len(d["ranked_candidates"]), 5)
        for c in d["ranked_candidates"]:
            for k in ("retrieval_score", "phenotype_score", "population", "population_contribution", "final_score", "rank", "baseline_rank", "rank_change"):
                self.assertIn(k, c)
            self.assertIn(c["population"]["status"], STATES)
            self.assertIn(c["population"]["indigen"]["status"], STATES)
            # IndiGen is unavailable: it must be reported as such, never as a number
            if d["population_coverage"]["indigen_dataset"] != "available":
                self.assertIn(c["population"]["indigen"]["status"], ("unavailable", "not_applicable"))  # no genes -> not_applicable
                self.assertIsNone(c["indian_population_signal"])
            if c["population"]["signal"] is None:
                self.assertEqual(c["population_contribution"], 0.0)

    def test_retrieval_candidates_unchanged_by_population_stage(self):
        r = self.client.post("/api/retrieve", json={"clinical_text": TEXT, "top_k": 50}).json()
        k = self.client.post("/api/rank", json={"clinical_text": TEXT, "top_k": 50}).json()
        retrieved = {c["disease_id"]: c["retrieval_score_norm"] for c in r["candidates"]}
        self.assertEqual(set(retrieved), {c["disease_id"] for c in k["ranked_candidates"]})
        for c in k["ranked_candidates"]:
            self.assertAlmostEqual(c["retrieval_score"], retrieved[c["disease_id"]], places=5)

    def test_diagnose_carries_population_coverage_and_rank_change(self):
        d = self.client.post("/api/diagnose", json={"clinical_text": TEXT, "top_k": 5}).json()
        self.assertIn("population_coverage", d)
        f = d["fused_candidates"][0]
        for k in ("population", "population_contribution", "baseline_rank", "rank_change"):
            self.assertIn(k, f)


if __name__ == "__main__":
    unittest.main()
