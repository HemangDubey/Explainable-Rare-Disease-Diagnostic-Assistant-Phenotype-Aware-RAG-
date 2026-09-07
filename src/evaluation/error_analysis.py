import os
import json
import yaml
import torch
import pandas as pd
import numpy as np
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForTokenClassification
from datasets import load_from_disk

def extract_entities_from_bio(tokens, labels):
    """
    Extracts text entity spans from token list and BIO labels.
    Returns list of entity strings.
    """
    entities = []
    current_entity = []

    for tok, label in zip(tokens, labels):
        if label == "B-PHENOTYPE":
            if current_entity:
                entities.append(" ".join(current_entity))
                current_entity = []
            clean_tok = tok.replace("##", "")
            current_entity.append(clean_tok)
        elif label == "I-PHENOTYPE":
            if current_entity:
                clean_tok = tok.replace("##", "")
                current_entity.append(clean_tok)
            else:
                # Malformed BIO: I without preceding B
                clean_tok = tok.replace("##", "")
                current_entity.append(clean_tok)
        else: # O
            if current_entity:
                entities.append(" ".join(current_entity))
                current_entity = []
    if current_entity:
        entities.append(" ".join(current_entity))

    return entities

def run_error_analysis(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    id2label = {int(k): v for k, v in config["labels"]["id2label"].items()}

    primary_model_dir = Path(config["models"]["primary"]["save_dir"])
    processed_dir = Path(config["dataset"]["processed_dir"]) / "primary"

    if not primary_model_dir.exists():
        print(f"ERROR: Primary model directory {primary_model_dir} does not exist. Train model first.")
        return

    print(f"Loading BiomedBERT model for error analysis from {primary_model_dir}")
    tokenizer = AutoTokenizer.from_pretrained(str(primary_model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(primary_model_dir))
    model.eval()

    ds_dict = load_from_disk(processed_dir)
    test_ds = ds_dict["test"]

    error_records = []
    error_counts = {
        "missed_phenotype": 0,
        "false_positive": 0,
        "boundary_error": 0,
        "multiple_phenotypes": 0
    }

    for item in test_ds:
        text = item["text"]
        input_ids = item["input_ids"]
        true_labels_raw = item["labels"]

        inputs = {
            "input_ids": torch.tensor([input_ids]),
            "attention_mask": torch.tensor([item["attention_mask"]])
        }

        with torch.no_grad():
            outputs = model(**inputs)
            preds_raw = torch.argmax(outputs.logits, dim=2)[0].tolist()

        tokens = tokenizer.convert_ids_to_tokens(input_ids)

        # Filter out special tokens (-100)
        valid_tokens = []
        true_bio = []
        pred_bio = []

        for tok, t_lbl, p_lbl in zip(tokens, true_labels_raw, preds_raw):
            if t_lbl != -100:
                valid_tokens.append(tok)
                true_bio.append(id2label.get(t_lbl, "O"))
                pred_bio.append(id2label.get(p_lbl, "O"))

        true_entities = extract_entities_from_bio(valid_tokens, true_bio)
        pred_entities = extract_entities_from_bio(valid_tokens, pred_bio)

        if true_entities != pred_entities:
            # Classify error type
            err_types = []
            
            # Missed phenotype (FN)
            for t_ent in true_entities:
                if t_ent not in pred_entities:
                    if any(t_ent in p_ent or p_ent in t_ent for p_ent in pred_entities):
                        err_types.append("boundary_error")
                        error_counts["boundary_error"] += 1
                    else:
                        err_types.append("missed_phenotype")
                        error_counts["missed_phenotype"] += 1

            # False Positive (FP)
            for p_ent in pred_entities:
                if p_ent not in true_entities and not any(p_ent in t_ent or t_ent in p_ent for t_ent in true_entities):
                    err_types.append("false_positive")
                    error_counts["false_positive"] += 1

            if len(true_entities) > 1:
                err_types.append("multiple_phenotypes")
                error_counts["multiple_phenotypes"] += 1

            if not err_types:
                err_types.append("boundary_error")

            error_records.append({
                "text": text,
                "true_phenotype": " | ".join(true_entities) if true_entities else "[NONE]",
                "predicted_phenotype": " | ".join(pred_entities) if pred_entities else "[NONE]",
                "error_type": ", ".join(list(set(err_types)))
            })

    df_errors = pd.DataFrame(error_records)
    csv_path = reports_dir / "error_analysis.csv"
    df_errors.to_csv(csv_path, index=False)

    summary_path = reports_dir / "error_analysis_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_test_examples": len(test_ds),
            "total_error_examples": len(error_records),
            "error_counts": error_counts
        }, f, indent=2)

    print(f"\nError analysis completed:")
    print(f"  Total test samples: {len(test_ds)}")
    print(f"  Total error samples: {len(error_records)}")
    print(f"  Saved reports to:\n    {csv_path}\n    {summary_path}")
    return df_errors

if __name__ == "__main__":
    run_error_analysis()
