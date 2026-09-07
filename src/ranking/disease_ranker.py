import os
import json
import yaml
import numpy as np
from pathlib import Path

from src.ranking.population_prior import PopulationPriorEngine

class DiseaseRanker:
    def __init__(self, config_path="configs/config.yaml", custom_weights=None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        weights = custom_weights or self.config.get("ranking", {})
        self.w_hpo = float(weights.get("hpo_weight", 0.50))
        self.w_ret = float(weights.get("retrieval_weight", 0.35))
        self.w_pop = float(weights.get("population_weight", 0.15))

        # Normalize weights so sum = 1.0
        total_w = self.w_hpo + self.w_ret + self.w_pop
        if total_w > 0:
            self.w_hpo /= total_w
            self.w_ret /= total_w
            self.w_pop /= total_w

        self.pop_engine = PopulationPriorEngine(config_path)

    def rank_candidates(self, candidates, exp_config="rag_indigen_gnomad"):
        """
        Reranks retrieved candidate diseases based on multi-component scoring.
        exp_config options:
          - 'rag_only': Phenotype + Retrieval only
          - 'rag_indigen': Phenotype + Retrieval + IndiGen Indian prior
          - 'rag_indigen_gnomad': Phenotype + Retrieval + IndiGen + gnomAD global baseline
        """
        ranked_list = []

        for cand in candidates:
            p_score = float(cand.get("hpo_match_score", 0.0))
            r_score = float(cand.get("embedding_similarity", 0.0))
            genes = cand.get("associated_genes", [])

            use_ind = exp_config in ["rag_indigen", "rag_indigen_gnomad"]
            use_gno = exp_config == "rag_indigen_gnomad"

            pop_res = self.pop_engine.compute_population_scores(genes, use_indigen=use_ind, use_gnomad=use_gno)
            ind_signal = pop_res["indian_population_signal"]
            gno_signal = pop_res["global_population_signal"]

            if exp_config == "rag_only":
                final_score = (self.w_hpo * p_score + self.w_ret * r_score) / (self.w_hpo + self.w_ret)
            elif exp_config == "rag_indigen":
                final_score = self.w_hpo * p_score + self.w_ret * r_score + self.w_pop * ind_signal
            else: # rag_indigen_gnomad
                pop_comb = 0.60 * ind_signal + 0.40 * gno_signal
                final_score = self.w_hpo * p_score + self.w_ret * r_score + self.w_pop * pop_comb

            ranked_list.append({
                "disease_id": cand.get("disease_id"),
                "disease_name": cand.get("disease_name"),
                "phenotype_score": float(round(p_score, 4)),
                "retrieval_score": float(round(r_score, 4)),
                "indian_population_signal": float(round(ind_signal, 4)),
                "global_population_signal": float(round(gno_signal, 4)),
                "final_score": float(round(final_score, 4)),
                "matched_hpo_ids": cand.get("matched_hpo_ids", []),
                "associated_phenotypes": cand.get("associated_phenotypes", []),
                "associated_genes": cand.get("associated_genes", []),
                "population_evidence_status": pop_res["population_evidence_status"],
                "evidence_sources": cand.get("source_db", "").split(",") + pop_res["evidence_sources"]
            })

        # Sort by final_score descending
        ranked_list.sort(key=lambda x: x["final_score"], reverse=True)

        for idx, item in enumerate(ranked_list, 1):
            item["rank"] = idx

        return ranked_list

if __name__ == "__main__":
    ranker = DiseaseRanker()
    dummy_cands = [
        {"disease_id": "OMIM:620790", "disease_name": "Disorder A", "hpo_match_score": 0.5, "embedding_similarity": 0.94, "associated_genes": ["OTUD7A"], "source_db": "OMIM"},
        {"disease_id": "OMIM:619639", "disease_name": "Disorder B", "hpo_match_score": 0.75, "embedding_similarity": 0.91, "associated_genes": ["UBE4A"], "source_db": "OMIM"}
    ]
    print(json.dumps(ranker.rank_candidates(dummy_cands), indent=2))
