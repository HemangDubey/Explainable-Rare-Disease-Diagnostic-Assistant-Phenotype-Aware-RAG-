import os
import time
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

from src.retrieval.disease_retriever import DiseaseRetriever

def evaluate_retrieval(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    disease_json = Path(config["disease"]["processed_dir"]) / config["disease"]["disease_kb_json"]
    disease_kb = json.load(open(disease_json, encoding="utf-8"))
    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    eval_cases = []
    for d_id, d_data in list(disease_kb.items())[:200]:
        if len(d_data.get("hpo_names", [])) >= 2:
            eval_cases.append({
                "target_disease_id": d_id,
                "phenotypes": d_data.get("hpo_names", [])[:5],
                "hpo_ids": d_data.get("hpo_ids", [])[:5]
            })

    comparison_results = []
    detailed_metrics = {}

    for model_key in ["primary", "baseline"]:
        m_name = config["retrieval"]["models"][model_key]["name"]
        retriever = DiseaseRetriever(model_key=model_key, config_path=config_path)

        rec1, rec5, rec10, mrr_list, latencies = [], [], [], [], []

        for case in eval_cases:
            t0 = time.time()
            candidates = retriever.retrieve_diseases(case["phenotypes"], input_hpo_ids=case["hpo_ids"], top_k=10)
            latencies.append((time.time() - t0) * 1000.0)

            ret_ids = [c["disease_id"] for c in candidates]
            rank = 0
            for r_idx, r_id in enumerate(ret_ids, 1):
                if r_id == case["target_disease_id"]:
                    rank = r_idx
                    break

            rec1.append(1.0 if rank == 1 else 0.0)
            rec5.append(1.0 if 1 <= rank <= 5 else 0.0)
            rec10.append(1.0 if 1 <= rank <= 10 else 0.0)
            mrr_list.append(1.0 / rank if rank > 0 else 0.0)

        res = {
            "Model": m_name,
            "Recall@1": round(float(np.mean(rec1)), 4),
            "Recall@5": round(float(np.mean(rec5)), 4),
            "Recall@10": round(float(np.mean(rec10)), 4),
            "MRR": round(float(np.mean(mrr_list)), 4),
            "Avg_Latency_ms": round(float(np.mean(latencies)), 2)
        }
        comparison_results.append(res)
        detailed_metrics[m_name] = res

    df_comp = pd.DataFrame(comparison_results)
    df_comp.to_csv(reports_dir / "retrieval_comparison.csv", index=False)
    with open(reports_dir / "retrieval_evaluation_detailed.json", "w", encoding="utf-8") as f:
        json.dump(detailed_metrics, f, indent=2)

    print("=== RETRIEVAL EVALUATION RESULTS ===")
    print(df_comp.to_string(index=False))
    return df_comp, detailed_metrics

if __name__ == "__main__":
    evaluate_retrieval()
