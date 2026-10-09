"""Phase 3 ranking pipeline - consumes the single Phase 2R retrieval pipeline.

No phenotype extraction happens here: phenotypes come from BiomedBERT NER -> HPO normalisation
inside Phase2RetrievalPipeline. Population re-ranking itself is unchanged (Phase 3R will replace
its synthetic population data).
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.abspath("."))
from src.pipeline.retrieval_pipeline import Phase2RetrievalPipeline
from src.ranking.disease_ranker import DiseaseRanker
from src.ranking.explanation import generate_ranking_explanation


class Phase3RankingPipeline:
    def __init__(self, model_key="primary", config_path="configs/config.yaml", retrieval_pipeline=None):
        self.retrieval = retrieval_pipeline or Phase2RetrievalPipeline(model_key=model_key, config_path=config_path)
        self.config = self.retrieval.config
        self.disease_ranker = DiseaseRanker(config_path=config_path)

    @staticmethod
    def population_coverage(ranked, pop_engine):
        """Actual evidence coverage over the returned candidates (no estimates)."""
        n = len(ranked)
        st = [c["population"] for c in ranked]
        return {
            "candidates": n,
            "gnomad_global_available": sum(p["gnomad_global"]["status"] == "available" for p in st),
            "gnomad_south_asian_available": sum(p["gnomad_south_asian"]["status"] == "available" for p in st),
            "sas_and_global_matched": sum(p["gnomad_south_asian"]["status"] == "available" and p["gnomad_global"]["status"] == "available" for p in st),
            "indigen_available": sum(p["indigen"]["status"] == "available" for p in st),
            "indigen_and_gnomad_matched": sum(p["indigen"]["status"] == "available" and p["gnomad_global"]["status"] == "available" for p in st),
            "signal_available": sum(p["signal"] is not None for p in st),
            "unavailable": sum(p["status"] in ("unavailable", "not_found", "not_applicable") for p in st),
            "indigen_dataset": "available" if pop_engine.lookup.indigen.available else "unavailable - access required",
            "signal_defined": pop_engine.lookup.cdf_global.n >= pop_engine.lookup.min_n,
            "reference_genes": pop_engine.lookup.cdf_global.n, "reference_genes_required": pop_engine.lookup.min_n,
            "population_weight": None,
        }

    def _rank(self, base, top_k_disease, exp_config):
        retrieved = base["candidate_diseases"]
        ranked = self.disease_ranker.rank_candidates(retrieved, exp_config=exp_config)[:top_k_disease]
        return ranked, retrieved

    def run(self, clinical_text, top_k_disease=10, exp_config="rag_south_asian_global", strategy=None):
        pool = max(top_k_disease, self.retrieval.candidate_pool)
        base = self.retrieval.run(clinical_text, top_k_disease=pool, strategy=strategy)
        ranked, retrieved = self._rank(base, top_k_disease, exp_config)
        return {
            "input_text": clinical_text,
            "phenotypes": base["phenotypes"],
            "hpo_mappings": base["hpo_mappings"],
            "hpo_terms": base["hpo_terms"],
            "unmatched_phenotypes": base["unmatched_phenotypes"],
            "retrieved_candidates": retrieved[:top_k_disease],
            "ranked_candidates": ranked,
            "ranking_explanations": [generate_ranking_explanation(c) for c in ranked],
            "rag_context": base["rag_context"],
            "retrieval_metadata": base["retrieval_metadata"],
            "population_coverage": {**self.population_coverage(ranked, self.disease_ranker.pop),
                                    "population_weight": self.disease_ranker.weights["w_population"]},
        }

    def run_from_hpo_terms(self, hpo_terms, top_k_disease=10, exp_config="rag_south_asian_global", strategy=None):
        """Same ranking for an explicit HPO term set (counterfactual what-if analysis)."""
        pool = max(top_k_disease, self.retrieval.candidate_pool)
        base = self.retrieval.run_from_hpo_terms(hpo_terms, pool, strategy)
        ranked, retrieved = self._rank(base, top_k_disease, exp_config)
        return {"hpo_terms": hpo_terms, "retrieved_candidates": retrieved[:top_k_disease], "ranked_candidates": ranked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, required=True)
    args = parser.parse_args()
    res = Phase3RankingPipeline().run(args.text)
    print(json.dumps({"top_ranked_candidate": res["ranked_candidates"][:1],
                      "hpo_terms": res["hpo_terms"], "unmatched": res["unmatched_phenotypes"]}, indent=2))
