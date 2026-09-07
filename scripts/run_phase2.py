import os
import sys
import argparse
import yaml
import json

sys.path.append(os.path.abspath("."))

from scripts.download_hpo_data import download_hpo_data
from src.knowledge.build_hpo_knowledge_base import build_knowledge_base
from src.retrieval.embed_knowledge_base import embed_knowledge_base
from src.retrieval.build_faiss_index import build_faiss_indices
from src.pipeline.retrieval_pipeline import Phase2RetrievalPipeline
from src.evaluation.evaluate_retrieval import evaluate_retrieval

def run_phase2_pipeline(rebuild=False, config_path="configs/config.yaml"):
    print("\n================ PHASE 2 PIPELINE ================")
    download_hpo_data(config_path)
    build_knowledge_base(config_path)
    embed_knowledge_base(config_path, rebuild=rebuild)
    build_faiss_indices(config_path, rebuild=rebuild)

    print("\nTesting Retrieval Pipeline...")
    pipeline = Phase2RetrievalPipeline(model_key="primary", config_path=config_path)
    sample_text = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
    res = pipeline.run(sample_text)
    print("\n--- END-TO-END RAG CONTEXT SAMPLE ---")
    print(res["rag_context"]["structured_markdown_context"])

    print("\nRunning Model Retrieval Benchmarking...")
    evaluate_retrieval(config_path)
    print("\n================ PHASE 2 COMPLETED SUCCESSFULLY ================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    run_phase2_pipeline(rebuild=args.rebuild)
