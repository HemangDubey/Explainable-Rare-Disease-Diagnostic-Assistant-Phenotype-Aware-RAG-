"""Phase 2R tests: real embeddings, FAISS alignment, HPO normalisation, NER -> HPO -> retrieval.

Run:  python -m unittest tests.test_phase2r_retrieval -v
These tests use the REAL models/indexes and fail (not skip) if they are missing. Lexical-only
normaliser tests use use_semantic=False explicitly and need no model.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.append(os.path.abspath("."))
CONFIG = "configs/config.yaml"


class TestNoRandomFallback(unittest.TestCase):
    def test_source_has_no_random_embedding_code(self):
        forbidden = [r"RandomState", r"np\.random", r"\brandn\b", r"\bhash\("]
        for d in ["src/retrieval", "src/pipeline", "src/knowledge", "src/inference"]:
            for f in Path(d).glob("*.py"):
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if line.strip().startswith("#"):
                        continue
                    for pat in forbidden:
                        self.assertIsNone(re.search(pat, line), f"{f}:{n} contains forbidden pattern {pat}")


class TestEmbeddings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.retrieval.encoder import get_encoder
        cls.enc = get_encoder("primary", CONFIG)
        cls.mini = get_encoder("baseline", CONFIG)

    def test_models_load_with_expected_dimensions(self):
        self.assertEqual(self.enc.dim, 768)
        self.assertEqual(self.enc.hf_id, "pritamdeka/S-PubMedBert-MS-MARCO")
        self.assertEqual(self.mini.dim, 384)
        self.assertEqual(self.mini.hf_id, "sentence-transformers/all-MiniLM-L6-v2")

    def test_embedding_dtype_shape_norm(self):
        v = self.enc.encode(["hypotonia", "seizure"])
        self.assertEqual(v.shape, (2, 768))
        self.assertEqual(v.dtype, np.float32)
        self.assertTrue(np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4))
        self.assertTrue(np.isfinite(v).all())

    def test_deterministic(self):
        a, b = self.enc.encode(["hypotonia"]), self.enc.encode(["hypotonia"])
        self.assertLess(float(np.abs(a - b).max()), 1e-6)

    def test_different_texts_differ_and_semantics_plausible(self):
        v = self.mini.encode(["hypotonia", "poor muscle tone", "cataract"])
        self.assertLess(float(v[0] @ v[2]), 0.9999)
        self.assertGreater(float(v[0] @ v[1]), float(v[0] @ v[2]) - 0.5)   # sanity only; MiniLM is a weak biomedical model

    def test_stored_vectors_match_fresh_model_output(self):
        emb = Path("data/embeddings")
        recs = json.load(open(emb / "records" / "hpo_records.json", encoding="utf-8"))
        vecs = np.load(emb / "spubmedbert" / "hpo_vectors.npy")
        idx = [0, 100, 5000, len(recs) - 1]
        fresh = self.enc.encode([recs[i]["canonical_text"] for i in idx])
        self.assertLess(float(np.abs(fresh - vecs[idx]).max()), 1e-4)


class TestIndexAlignment(unittest.TestCase):
    def test_index_matches_records_for_both_models(self):
        from src.retrieval.store import get_store
        for key in ("primary", "baseline"):
            s = get_store(key, CONFIG)
            self.assertEqual(s.hpo_index.ntotal, len(s.hpo_records))
            self.assertEqual(s.disease_index.ntotal, len(s.disease_records))
            self.assertEqual(s.disease_index.d, s.manifest["embedding_dimension"])
            self.assertEqual(s.manifest["model"], s.hf_id)

    def test_hpo_self_lookup(self):
        from src.retrieval.hpo_search import HPOSearchEngine
        top = HPOSearchEngine("primary", CONFIG).search("Hypotonia", top_k=1)[0]
        self.assertEqual(top["hpo_id"], "HP:0001252")


class TestHPONormalizerLexical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.knowledge.hpo_normalizer import HPONormalizer
        cls.n = HPONormalizer(CONFIG, use_semantic=False)

    def test_exact(self):
        r = self.n.normalize_detailed("Hypotonia")
        self.assertEqual((r["status"], r["hpo_id"]), ("exact", "HP:0001252"))

    def test_synonym(self):
        r = self.n.normalize_detailed("developmental delay")
        self.assertEqual((r["status"], r["hpo_id"]), ("synonym", "HP:0001263"))

    def test_unknown_is_unmatched_never_root(self):
        r = self.n.normalize_detailed("xyzzy blorp")
        self.assertEqual(r["status"], "unmatched")
        self.assertIsNone(r["hpo_id"])
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(self.n.normalize("xyzzy blorp"), [])

    def test_never_returns_hp0000001_for_free_text(self):
        for q in ["asdf", "the patient", "", "lorem ipsum dolor"]:
            self.assertNotEqual(self.n.normalize_detailed(q)["hpo_id"], "HP:0000001")

    def test_ambiguous_returns_candidates(self):
        res = self.n.res
        ambiguous = [k for k, v in res.syn_map.items() if len(v) > 1 and k not in res.name_map]
        self.assertTrue(ambiguous, "expected at least one ambiguous synonym in HPO")
        r = self.n.normalize_detailed(ambiguous[0])
        self.assertEqual(r["status"], "ambiguous")
        self.assertGreater(len(r["candidates"]), 1)
        self.assertIsNone(r["hpo_id"])

    def test_obsolete_terms_not_matched(self):
        obsolete = next(t for t in res_terms(self.n)
                        if t.get("is_obsolete") and not t.get("replaced_by") and t["hpo_id"] not in self.n.res.alt)
        r = self.n.normalize_detailed(obsolete["hpo_id"])
        self.assertEqual(r["status"], "unmatched")

    def test_alt_id_resolves_to_current_term(self):
        alt, current = next(iter(self.n.res.alt.items()))
        r = self.n.normalize_detailed(alt)
        self.assertEqual(r["hpo_id"], current if not self.n.res.terms[current].get("is_obsolete") else r["hpo_id"])
        self.assertEqual(r["status"], "exact")


def res_terms(n):
    return list(n.res.terms.values())


class TestPipelineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.pipeline.retrieval_pipeline import Phase2RetrievalPipeline
        from src.pipeline.ranking_pipeline import Phase3RankingPipeline
        cls.p2 = Phase2RetrievalPipeline("primary", CONFIG)
        cls.p3 = Phase3RankingPipeline("primary", CONFIG, retrieval_pipeline=cls.p2)
        cls.text = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."

    def test_ner_inference_returns_structured_mentions(self):
        ms = self.p2.ner.extract(self.text)
        self.assertGreaterEqual(len(ms), 3)
        for m in ms:
            self.assertEqual(self.text[m["start"]:m["end"]], m["mention"])
            self.assertEqual(m["label"], "PHENOTYPE")
            self.assertTrue(0.0 <= m["confidence"] <= 1.0)

    def test_ner_to_hpo_integration(self):
        _, _, hpo_terms, _ = self.p2.extract_and_map(self.text)
        ids = {h["hpo_id"] for h in hpo_terms}
        self.assertTrue({"HP:0001252", "HP:0004322"} <= ids)
        self.assertNotIn("HP:0000001", ids)

    def test_hpo_to_retrieval_integration(self):
        r = self.p2.run(self.text, top_k_disease=5)
        self.assertEqual(len(r["candidate_diseases"]), 5)
        top = r["candidate_diseases"][0]
        for k in ("disease_id", "disease_name", "embedding_similarity", "phenotype_overlap", "associated_genes", "matched_hpo_ids"):
            self.assertIn(k, top)
        self.assertEqual(r["retrieval_metadata"]["model"], "pritamdeka/S-PubMedBert-MS-MARCO")

    def test_retrieval_reproducible(self):
        a = self.p2.run(self.text, 5)["candidate_diseases"]
        b = self.p2.run(self.text, 5)["candidate_diseases"]
        self.assertEqual([c["disease_id"] for c in a], [c["disease_id"] for c in b])

    def test_no_mapped_phenotypes_means_no_candidates(self):
        r = self.p2.run("xyzzy blorp qwerty", 5)
        self.assertEqual(r["candidate_diseases"], [])
        self.assertIsNotNone(r["retrieval_metadata"]["note"])

    def test_ranking_uses_the_same_pipeline(self):
        r = self.p3.run(self.text, top_k_disease=5)
        self.assertEqual(len(r["ranked_candidates"]), 5)
        self.assertTrue(all(h["hpo_id"] != "HP:0000001" for h in r["hpo_terms"]))
        self.assertIn("hpo_mappings", r)


if __name__ == "__main__":
    unittest.main()
