import os
import sys
import json
import yaml
import argparse
from pathlib import Path

sys.path.append(os.path.abspath("."))

from src.population.inspect_population_data import inspect_population_data
from src.population.indigen_processor import process_indigen_data
from src.population.gnomad_processor import process_gnomad_data
from src.population.frequency_comparator import compare_frequencies
from src.retrieval.embed_knowledge_base import embed_knowledge_base
from src.retrieval.build_faiss_index import build_faiss_indices
from src.ranking.tune_weights import tune_ranking_weights
from src.evaluation.evaluate_ranking import evaluate_ranking
from src.pipeline.ranking_pipeline import Phase3RankingPipeline

def run_phase3_pipeline(config_path="configs/config.yaml", rebuild=False):
    print("\n============================================================")
    print("PHASE 3 — INDIAN POPULATION PRIORS + DISEASE RE-RANKING")
    print("============================================================")

    # 1. Inspect Population Data
    print("\n--- 1. Inspecting Population Data Sources ---")
    inspect_population_data(config_path)

    # 2. Process IndiGen Data
    print("\n--- 2. Processing IndiGen Indian Population Data ---")
    process_indigen_data(config_path)

    # 3. Process gnomAD Data
    print("\n--- 3. Processing gnomAD Global/SAS Baseline Data ---")
    process_gnomad_data(config_path)

    # 4. Compare Frequency Distributions
    print("\n--- 4. Computing Frequency Comparisons & Ratios ---")
    compare_frequencies(config_path)

    # 5. Verify Embeddings & Vector Index
    print("\n--- 5. Verifying Knowledge Base Embeddings & Vector DB ---")
    embed_knowledge_base(config_path, rebuild=rebuild)
    build_faiss_indices(config_path, rebuild=rebuild)

    # 6. Grid Search Weight Tuning
    print("\n--- 6. Tuning Reranking Weights on Validation Cases ---")
    tune_ranking_weights(config_path)

    # 7. Comparative Ablation Study
    print("\n--- 7. Running RAG-Only vs Population-Aware Ablation Study ---")
    evaluate_ranking(config_path)

    # 8. Test End-to-End Pipeline Execution
    print("\n--- 8. Testing End-to-End Pipeline on Sample Clinical Case ---")
    pipeline = Phase3RankingPipeline(model_key="primary", config_path=config_path)
    sample_text = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
    res = pipeline.run(sample_text)

    print("\n=== SAMPLE RANKED CANDIDATE DISEASES ===")
    for cand in res["ranked_candidates"][:5]:
        print(f"[{cand['rank']}] {cand['disease_name']} ({cand['disease_id']})")
        print(f"    Final Score: {cand['final_score']} | Phenotype: {cand['phenotype_score']} | Retrieval: {cand['retrieval_score']} | IndiGen Prior: {cand['indian_population_signal']}")
        print(f"    Matched HPO: {', '.join(cand['matched_hpo_ids'])} | Genes: {', '.join(cand['associated_genes'])}")

    print("\n=== SAMPLE CLINICAL EXPLANATION ===")
    print(res["ranking_explanations"][0] if res["ranking_explanations"] else "No explanation generated.")

    print("\n============================================================")
    print("PHASE 3 PIPELINE COMPLETED SUCCESSFULLY")
    print("============================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    run_phase3_pipeline(rebuild=args.rebuild)
