import unittest
from src.scribe.scribe_engine import ClinicalScribeEngine
from src.counterfactual.counterfactual_engine import CounterfactualEngine
from src.counterfactual.schemas import CounterfactualRequest
from src.pipeline.ranking_pipeline import Phase3RankingPipeline

class TestPhase5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranking_pipeline = Phase3RankingPipeline()
        cls.scribe_engine = ClinicalScribeEngine()
        cls.counterfactual_engine = CounterfactualEngine(ranking_pipeline=cls.ranking_pipeline)

    def test_clinical_scribe_extraction(self):
        text = "Patient is a 7-year-old child with developmental delay since infancy, hypotonia, short stature and recurrent seizures. No known family history."
        res = self.scribe_engine.extract_structured_case(text)

        self.assertIsNotNone(res.case_id)
        self.assertEqual(res.structured_case.age, "7-year-old")
        self.assertTrue(len(res.hpo_terms) > 0)
        self.assertTrue(any("family history" in neg.lower() for neg in res.structured_case.relevant_negatives))
        self.assertTrue(len(res.missing_information) > 0)

    def test_counterfactual_remove_phenotype(self):
        req = CounterfactualRequest(
            clinical_text="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.",
            operation="remove",
            phenotype_id="HP:0001250",
            top_k=5
        )
        res = self.counterfactual_engine.run_analysis(req, case_store={})

        self.assertIsNotNone(res.experiment_id)
        self.assertEqual(res.operation, "remove")
        self.assertTrue(len(res.baseline_ranking) > 0)
        self.assertTrue(len(res.counterfactual_ranking) > 0)
        self.assertTrue(len(res.ranking_deltas) > 0)
        self.assertTrue(len(res.phenotype_impacts) > 0)
        self.assertTrue(len(res.insights) > 0)

    def test_counterfactual_add_phenotype(self):
        req = CounterfactualRequest(
            clinical_text="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.",
            operation="add",
            phenotype_id="Facial dysmorphism",
            top_k=5
        )
        res = self.counterfactual_engine.run_analysis(req, case_store={})

        self.assertEqual(res.operation, "add")
        self.assertTrue(len(res.modified_phenotypes) > len(res.baseline_phenotypes))
        self.assertTrue(len(res.ranking_deltas) > 0)

    def test_counterfactual_compare_states(self):
        req = CounterfactualRequest(
            clinical_text="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.",
            operation="compare",
            modified_phenotypes=["Hypotonia", "Microcephaly"],
            top_k=5
        )
        res = self.counterfactual_engine.run_analysis(req, case_store={})

        self.assertEqual(res.operation, "compare")
        self.assertEqual(len(res.modified_phenotypes), 2)
        self.assertTrue(len(res.ranking_deltas) > 0)

if __name__ == "__main__":
    unittest.main()
