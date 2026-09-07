import os
import json
import yaml
import torch
import pandas as pd
import numpy as np
from pathlib import Path
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    Trainer,
    DataCollatorForTokenClassification
)
from datasets import load_from_disk
import evaluate

def evaluate_models(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    seqeval = evaluate.load("seqeval")
    id2label = {int(k): v for k, v in config["labels"]["id2label"].items()}

    comparison_results = []
    detailed_metrics = {}

    for model_key in ["primary", "baseline"]:
        model_info = config["models"][model_key]
        model_name = model_info["name"]
        save_dir = Path(model_info["save_dir"])
        processed_dir = Path(config["dataset"]["processed_dir"]) / model_key

        has_model_file = (save_dir / "model.safetensors").exists() or (save_dir / "pytorch_model.bin").exists()
        if not save_dir.exists() or not has_model_file:
            print(f"WARNING: Completed model checkpoint not found in {save_dir}. Skipping evaluation for {model_name}.")
            continue

        print(f"\nEvaluating Model: {model_name} from {save_dir}")
        tokenizer = AutoTokenizer.from_pretrained(str(save_dir))
        model = AutoModelForTokenClassification.from_pretrained(str(save_dir))

        ds_dict = load_from_disk(processed_dir)
        test_dataset = ds_dict["test"]

        data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)
        trainer = Trainer(
            model=model,
            processing_class=tokenizer,
            data_collator=data_collator,
        )

        predictions_output = trainer.predict(test_dataset)
        preds = np.argmax(predictions_output.predictions, axis=2)
        labels = predictions_output.label_ids

        true_predictions = [
            [id2label[p_idx] for (p_idx, l_idx) in zip(prediction, label) if l_idx != -100]
            for prediction, label in zip(preds, labels)
        ]
        true_labels = [
            [id2label[l_idx] for (p_idx, l_idx) in zip(prediction, label) if l_idx != -100]
            for prediction, label in zip(preds, labels)
        ]

        metrics = seqeval.compute(predictions=true_predictions, references=true_labels)

        prec = float(metrics["overall_precision"])
        rec = float(metrics["overall_recall"])
        f1 = float(metrics["overall_f1"])
        acc = float(metrics["overall_accuracy"])

        print(f"--- {model_name} Test Results ---")
        print(f"  Precision: {prec:.4f}")
        print(f"  Recall:    {rec:.4f}")
        print(f"  F1 Score:  {f1:.4f}")
        print(f"  Accuracy:  {acc:.4f}")

        row = {
            "Model": model_name,
            "Precision": round(prec, 4),
            "Recall": round(rec, 4),
            "F1": round(f1, 4),
            "Token_Accuracy": round(acc, 4)
        }
        comparison_results.append(row)

        detailed_metrics[model_name] = {
            "overall_precision": prec,
            "overall_recall": rec,
            "overall_f1": f1,
            "overall_accuracy": acc
        }

    # Export comparison table CSV
    df_comp = pd.DataFrame(comparison_results)
    csv_path = reports_dir / "ner_model_comparison.csv"
    df_comp.to_csv(csv_path, index=False)

    json_path = reports_dir / "ner_evaluation_detailed.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(detailed_metrics, f, indent=2)

    print(f"\nEvaluation reports saved to:\n  {csv_path}\n  {json_path}")
    return df_comp, detailed_metrics

if __name__ == "__main__":
    evaluate_models()
