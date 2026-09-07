import os
import time
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

from src.retrieval.disease_retriever import DiseaseRetriever
from src.ranking.disease_ranker import DiseaseRanker

def evaluate_ranking(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    disease_json = Path(config["disease"]["processed_dir"]) / config["disease"]["disease_kb_json"]
    disease_kb = json.load(open(disease_json, encoding="utf-8"))
    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    eval_cases = []
    for d_id, d_data in list(disease_kb.items())[:50]:
        if len(d_data.get("hpo_names", [])) >= 2:
            eval_cases.append({
                "target_disease_id": d_id,
                "phenotypes": d_data.get("hpo_names", [])[:5],
                "hpo_ids": d_data.get("hpo_ids", [])[:5]
            })

    retriever = DiseaseRetriever(model_key="primary", config_path=config_path)
    ranker = DiseaseRanker(config_path=config_path)

    case_retried = []
    for case in eval_cases:
        cands = retriever.retrieve_diseases(case["phenotypes"], input_hpo_ids=case["hpo_ids"], top_k=20)
        case_retried.append((case["target_disease_id"], cands))

    experiments = [
        ("Experiment A: RAG-Only", "rag_only"),
        ("Experiment B: RAG + Indian Prior", "rag_indigen"),
        ("Experiment C: RAG + Indian + Global Baseline", "rag_indigen_gnomad")
    ]

    ablation_results = []
    detailed_metrics = {}

    for exp_name, exp_cfg in experiments:
        rec1, rec5, rec10, mrr_list, latencies = [], [], [], [], []

        for target_id, cands in case_retried:
            t0 = time.time()
            ranked_cands = ranker.rank_candidates(cands, exp_config=exp_cfg)
            latencies.append((time.time() - t0) * 1000.0)

            ret_ids = [c["disease_id"] for c in ranked_cands]
            rank = next((r_idx for r_idx, r_id in enumerate(ret_ids, 1) if r_id == target_id), 0)

            rec1.append(1.0 if rank == 1 else 0.0)
            rec5.append(1.0 if 1 <= rank <= 5 else 0.0)
            rec10.append(1.0 if 1 <= rank <= 10 else 0.0)
            mrr_list.append(1.0 / rank if rank > 0 else 0.0)

        res = {
            "Configuration": exp_name,
            "Recall@1": round(float(np.mean(rec1)), 4),
            "Recall@5": round(float(np.mean(rec5)), 4),
            "Recall@10": round(float(np.mean(rec10)), 4),
            "MRR": round(float(np.mean(mrr_list)), 4),
            "Avg_Rerank_Latency_ms": round(float(np.mean(latencies)), 3)
        }
        ablation_results.append(res)
        detailed_metrics[exp_name] = res

    df_ablation = pd.DataFrame(ablation_results)
    df_ablation.to_csv(reports_dir / "ranking_ablation.csv", index=False)
    with open(reports_dir / "ranking_evaluation.json", "w", encoding="utf-8") as f:
        json.dump(detailed_metrics, f, indent=2)

    print("\n=== PHASE 3 DISEASE RE-RANKING ABLATION RESULTS ===")
    print(df_ablation.to_string(index=False))
    return df_ablation, detailed_metrics

if __name__ == "__main__":
    evaluate_ranking()
