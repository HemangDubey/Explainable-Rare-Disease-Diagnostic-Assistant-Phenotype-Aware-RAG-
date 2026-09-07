import os
import time
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

from src.retrieval.disease_retriever import DiseaseRetriever
from src.ranking.population_prior import PopulationPriorEngine

def tune_ranking_weights(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    disease_json = Path(config["disease"]["processed_dir"]) / config["disease"]["disease_kb_json"]
    disease_kb = json.load(open(disease_json, encoding="utf-8"))

    val_cases = []
    for d_id, d_data in list(disease_kb.items())[:50]:
        if len(d_data.get("hpo_names", [])) >= 2:
            val_cases.append({
                "target_disease_id": d_id,
                "phenotypes": d_data.get("hpo_names", [])[:5],
                "hpo_ids": d_data.get("hpo_ids", [])[:5]
            })

    retriever = DiseaseRetriever(model_key="primary", config_path=config_path)
    pop_engine = PopulationPriorEngine(config_path)

    precomputed_cases = []
    for case in val_cases:
        cands = retriever.retrieve_diseases(case["phenotypes"], input_hpo_ids=case["hpo_ids"], top_k=20)
        parsed_cands = []
        for c in cands:
            p_s = float(c.get("hpo_match_score", 0.0))
            r_s = float(c.get("embedding_similarity", 0.0))
            pop_res = pop_engine.compute_population_scores(c.get("associated_genes", []))
            pop_s = 0.60 * pop_res["indian_population_signal"] + 0.40 * pop_res["global_population_signal"]
            parsed_cands.append({
                "disease_id": c.get("disease_id"),
                "phenotype_score": p_s,
                "retrieval_score": r_s,
                "population_score": pop_s
            })
        precomputed_cases.append((case["target_disease_id"], parsed_cands))

    grid_results = []
    best_mrr = -1.0
    best_weights = {}

    for w_hpo in [0.30, 0.40, 0.50, 0.60]:
        for w_ret in [0.20, 0.30, 0.35, 0.40]:
            for w_pop in [0.05, 0.10, 0.15, 0.20]:
                tot = w_hpo + w_ret + w_pop
                wh, wr, wp = w_hpo / tot, w_ret / tot, w_pop / tot

                rec1, rec5, rec10, mrr_list = [], [], [], []

                for target_id, cands in precomputed_cases:
                    scored = []
                    for c in cands:
                        f_s = wh * c["phenotype_score"] + wr * c["retrieval_score"] + wp * c["population_score"]
                        scored.append((c["disease_id"], f_s))
                    scored.sort(key=lambda x: x[1], reverse=True)

                    ret_ids = [s[0] for s in scored]
                    rank = next((r_idx for r_idx, r_id in enumerate(ret_ids, 1) if r_id == target_id), 0)

                    rec1.append(1.0 if rank == 1 else 0.0)
                    rec5.append(1.0 if 1 <= rank <= 5 else 0.0)
                    rec10.append(1.0 if 1 <= rank <= 10 else 0.0)
                    mrr_list.append(1.0 / rank if rank > 0 else 0.0)

                mean_mrr = float(np.mean(mrr_list))
                res = {
                    "hpo_weight": round(float(w_hpo), 2),
                    "retrieval_weight": round(float(w_ret), 2),
                    "population_weight": round(float(w_pop), 2),
                    "Recall@1": round(float(np.mean(rec1)), 4),
                    "Recall@5": round(float(np.mean(rec5)), 4),
                    "Recall@10": round(float(np.mean(rec10)), 4),
                    "MRR": round(mean_mrr, 4)
                }
                grid_results.append(res)

                if mean_mrr > best_mrr:
                    best_mrr = mean_mrr
                    best_weights = res

    df_grid = pd.DataFrame(grid_results)
    df_grid.sort_values(by="MRR", ascending=False, inplace=True)

    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_out = reports_dir / "ranking_weight_search.csv"
    json_out = reports_dir / "best_ranking_weights.json"

    df_grid.to_csv(csv_out, index=False)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(best_weights, f, indent=2)

    print(f"Weight Tuning Complete -> Best Weights (MRR={best_weights['MRR']}): {best_weights}")
    return df_grid, best_weights

if __name__ == "__main__":
    tune_ranking_weights()
