"""Phase 2R API tests (FastAPI TestClient, real models). Run: python -m unittest tests.test_phase2r_api -v"""
import os
import sys
import unittest

sys.path.append(os.path.abspath("."))
from fastapi.testclient import TestClient  # noqa: E402
from tests.helpers_auth import authed_client, use_temp_database  # noqa: E402

use_temp_database()

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


class TestPhase2RApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.api.main import app
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()
        authed_client(cls.client)      # runs the startup event

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_health_reports_real_model(self):
        r = self.client.get("/").json()
        self.assertEqual(r["status"], "healthy")
        self.assertEqual(r["retrieval"]["model"], "pritamdeka/S-PubMedBert-MS-MARCO")

    def test_retrieve_contract(self):
        r = self.client.post("/api/retrieve", json={"clinical_text": TEXT, "top_k": 5})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("clinical_text", "extracted_phenotypes", "hpo_mappings", "candidates", "retrieval_metadata"):
            self.assertIn(k, d)
        self.assertEqual(len(d["candidates"]), 5)
        self.assertEqual(d["retrieval_metadata"]["top_k"], 5)
        self.assertTrue(all(m["status"] != "unmatched" or m["hpo_id"] is None for m in d["hpo_mappings"]))
        self.assertNotIn("HP:0000001", [m["hpo_id"] for m in d["hpo_mappings"]])

    def test_retrieve_empty_text_rejected(self):
        self.assertEqual(self.client.post("/api/retrieve", json={"clinical_text": "  "}).status_code, 400)

    def test_diagnose_uses_ner_pipeline(self):
        r = self.client.post("/api/diagnose", json={"text": TEXT, "top_k": 5})
        self.assertEqual(r.status_code, 200, r.text[:300])
        d = r.json()
        self.assertTrue(d["extracted_phenotypes"])
        # NER output carries character offsets and confidences (the old comma-splitter did not)
        self.assertIn("confidence", d["extracted_phenotypes"][0])
        self.assertNotEqual(d["extracted_phenotypes"][0].get("span"), "N/A")
        self.assertEqual(len(d["fused_candidates"]), 5)
        self.assertEqual(d["retrieval_metadata"]["ner_model"].split()[0], "BiomedBERT")

    def test_rank_endpoint(self):
        r = self.client.post("/api/rank", json={"clinical_text": TEXT, "top_k": 3})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["ranked_candidates"]), 3)


if __name__ == "__main__":
    unittest.main()
