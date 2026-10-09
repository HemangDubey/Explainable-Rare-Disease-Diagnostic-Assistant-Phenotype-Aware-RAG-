"""Phase 2R master script: KB -> REAL embeddings -> FAISS -> validation -> evaluation.

    python scripts/run_phase2.py            # reuse existing artifacts
    python scripts/run_phase2.py --rebuild  # regenerate embeddings + indexes (long on CPU)
"""
import argparse
import os
import sys

sys.path.append(os.path.abspath("."))

from scripts.download_hpo_data import download_hpo_data
from scripts.validate_embeddings import validate
from src.evaluation.evaluate_hpo_normalization import run as evaluate_hpo_normalization
from src.evaluation.evaluate_retrieval import evaluate_retrieval
from src.knowledge.build_hpo_knowledge_base import build_knowledge_base
from src.retrieval.build_faiss_index import build_faiss_indices
from src.retrieval.embed_knowledge_base import embed_knowledge_base


def run_phase2_pipeline(rebuild=False, config_path="configs/config.yaml"):
    print("\n================ PHASE 2R PIPELINE ================")
    download_hpo_data(config_path)
    build_knowledge_base(config_path)
    embed_knowledge_base(config_path, rebuild=rebuild)       # real S-PubMedBERT + MiniLM; raises if models unavailable
    build_faiss_indices(config_path, rebuild=rebuild)
    report = validate(config_path)
    if not report["passed"]:
        raise SystemExit("Embedding validation FAILED - see reports/embedding_validation.json")
    evaluate_hpo_normalization(config_path)
    evaluate_retrieval(config_path)
    print("\n================ PHASE 2R COMPLETED ================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    run_phase2_pipeline(rebuild=args.rebuild)
