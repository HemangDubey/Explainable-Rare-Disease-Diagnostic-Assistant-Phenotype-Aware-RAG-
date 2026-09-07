import os
import sys
import argparse
import yaml
from pathlib import Path

# Add src and scripts to path
sys.path.append(os.path.abspath("."))

from scripts.download_dataset import download_dataset
from scripts.inspect_dataset import inspect_dataset
from src.data.convert_to_bio import convert_dataset_to_bio
from src.models.train_biomedbert import train_biomedbert
from src.models.train_biobert import train_biobert
from src.evaluation.evaluate_ner import evaluate_models
from src.evaluation.error_analysis import run_error_analysis

def run_phase1_pipeline(force=False, config_path="configs/config.yaml"):
    print("\n=======================================================")
    print("      PHASE 1: PHENOTYPE NER TRAINING PIPELINE         ")
    print("=======================================================\n")

    # Step 1: Download / Verify Dataset
    print("\n[STEP 1/7] Data Acquisition & Verification...")
    if not download_dataset(config_path):
        print("Pipeline stopped at Step 1 due to dataset acquisition failure.")
        sys.exit(1)

    # Step 2: Inspect Dataset
    print("\n[STEP 2/7] Dataset Inspection & Statistics...")
    try:
        inspect_dataset(config_path)
    except Exception as e:
        print(f"Pipeline stopped at Step 2 due to error: {e}")
        sys.exit(1)

    # Step 3: Convert to BIO Format
    print("\n[STEP 3/7] BIO Tagging & Tokenizer Alignment...")
    try:
        convert_dataset_to_bio(config_path)
    except Exception as e:
        print(f"Pipeline stopped at Step 3 due to error: {e}")
        sys.exit(1)

    # Step 4: Fine-tune Model 1 (BiomedBERT)
    print("\n[STEP 4/7] Fine-tuning BiomedBERT (Primary Model)...")
    try:
        train_biomedbert(config_path, force=force)
    except Exception as e:
        print(f"Pipeline stopped at Step 4 due to error: {e}")
        sys.exit(1)

    # Step 5: Fine-tune Model 2 (BioBERT)
    print("\n[STEP 5/7] Fine-tuning BioBERT (Baseline Model)...")
    try:
        train_biobert(config_path, force=force)
    except Exception as e:
        print(f"Pipeline stopped at Step 5 due to error: {e}")
        sys.exit(1)

    # Step 6: Evaluation & Model Comparison
    print("\n[STEP 6/7] Test Set Evaluation & Model Comparison...")
    try:
        evaluate_models(config_path)
    except Exception as e:
        print(f"Pipeline stopped at Step 6 due to error: {e}")
        sys.exit(1)

    # Step 7: Error Analysis
    print("\n[STEP 7/7] Error Analysis on Test Set...")
    try:
        run_error_analysis(config_path)
    except Exception as e:
        print(f"Pipeline stopped at Step 7 due to error: {e}")
        sys.exit(1)

    print("\n=======================================================")
    print("  PHASE 1 PIPELINE COMPLETED SUCCESSFULLY!            ")
    print("=======================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master Pipeline for Phase 1: Phenotype NER Training")
    parser.add_argument("--force", action="store_true", help="Force retraining of existing model checkpoints")
    parser.add_argument("--config", type=str, default="configs/config.yaml", help="Path to config file")
    args = parser.parse_args()

    run_phase1_pipeline(force=args.force, config_path=args.config)
