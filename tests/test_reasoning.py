import os
import sys
sys.path.append(os.path.abspath("."))
import unittest
import yaml
from src.reasoning.evidence_fusion import EvidenceFusionEngine
from src.reasoning.differential import DifferentialEngine

class TestPhase4Reasoning(unittest.TestCase):
    def setUp(self):
        with open("configs/config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.fusion = EvidenceFusionEngine(self.config)
        self.differential = DifferentialEngine(self.config)

    def test_evidence_fusion_valid_candidate(self):
        sample_candidate = {
            "disease_id": "OMIM:620790",
            "disease_name": "Neurodevelopmental disorder with hypotonia and seizures",
            "final_score": 0.7812,
            "phenotype_score": 0.50,
            "retrieval_score": 0.9469,
            "indian_population_signal": 0.6412,
            "global_population_signal": 0.5210,
            "population_evidence_status": "available",
            "matched_hpo_ids": ["HP:0001252", "HP:0001263"],
            "associated_phenotypes": ["Hypotonia", "Global developmental delay", "Seizures", "Ataxia"],
            "associated_genes": ["OTUD7A"],
            "evidence_sources": ["OMIM", "HPO", "IndiGen"]
        }
        extracted_phenotypes = [{"phenotype": "hypotonia"}, {"phenotype": "seizures"}]
        hpo_terms = [
            {"hpo_id": "HP:0001252", "name": "Hypotonia"},
            {"hpo_id": "HP:0001263", "name": "Global developmental delay"}
        ]

        fused = self.fusion.fuse_candidate_evidence(
            candidate=sample_candidate,
            extracted_phenotypes=extracted_phenotypes,
            hpo_terms=hpo_terms,
            rank=1
        )

        self.assertEqual(fused["rank"], 1)
        self.assertEqual(fused["disease_id"], "OMIM:620790")
        self.assertEqual(fused["phenotype_evidence"]["confidence"], "Moderate")
        self.assertEqual(fused["retrieval_evidence"]["confidence"], "High")
        self.assertEqual(fused["population_evidence"]["category"], "SUPPORTING")
        self.assertTrue(len(fused["evidence_items"]) >= 4)

    def test_evidence_fusion_missing_population(self):
        sample_candidate = {
            "disease_id": "ORPHA:12345",
            "disease_name": "Ultra-rare Syndromic Disorder",
            "final_score": 0.6120,
            "phenotype_score": 0.40,
            "retrieval_score": 0.8200,
            "indian_population_signal": 0.50,
            "global_population_signal": 0.50,
            "population_evidence_status": "not_found",
            "matched_hpo_ids": ["HP:0001252"],
            "associated_phenotypes": ["Hypotonia"],
            "associated_genes": ["XYZ1"],
            "evidence_sources": ["Orphanet"]
        }
        fused = self.fusion.fuse_candidate_evidence(
            candidate=sample_candidate,
            extracted_phenotypes=[],
            hpo_terms=[],
            rank=2
        )
        self.assertEqual(fused["population_evidence"]["status"], "not_found")
        self.assertEqual(fused["population_evidence"]["category"], "NEUTRAL")
        self.assertEqual(fused["population_evidence"]["confidence"], "Unknown")

    def test_differential_diagnosis_generation(self):
        fused_cands = [
            {
                "rank": 1,
                "disease_id": "OMIM:1001",
                "disease_name": "Disorder A",
                "final_score": 0.85,
                "phenotype_evidence": {"score": 0.8, "confidence": "High", "matched_phenotypes": [{"name": "Hypotonia"}, {"name": "Microcephaly"}], "missing_phenotypes": ["Cardiac murmur"]},
                "retrieval_evidence": {"score": 0.9, "confidence": "High"},
                "population_evidence": {"indian_signal": 0.65, "global_signal": 0.52, "status": "available"},
                "genes": ["GENE1"]
            },
            {
                "rank": 2,
                "disease_id": "OMIM:1002",
                "disease_name": "Disorder B",
                "final_score": 0.72,
                "phenotype_evidence": {"score": 0.6, "confidence": "Moderate", "matched_phenotypes": [{"name": "Hypotonia"}], "missing_phenotypes": ["Syndactyly"]},
                "retrieval_evidence": {"score": 0.85, "confidence": "High"},
                "population_evidence": {"indian_signal": 0.50, "global_signal": 0.50, "status": "not_found"},
                "genes": ["GENE2"]
            }
        ]

        diff = self.differential.generate_differential(fused_cands, "Sample case text")
        self.assertEqual(len(diff["top_candidates"]), 2)
        self.assertEqual(len(diff["comparisons"]), 1)
        self.assertIn("Microcephaly", diff["comparisons"][0]["primary_differentiating_phenotypes"])
        self.assertIn("disclaimer", diff)

if __name__ == "__main__":
    unittest.main()
