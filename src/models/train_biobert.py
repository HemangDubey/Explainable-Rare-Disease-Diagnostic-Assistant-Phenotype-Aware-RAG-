import os
import sys
import json
import yaml
import torch
import numpy as np
import pandas as pd
from pathlib import Path
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    set_seed
)
from datasets import load_from_disk
import evaluate

def compute_metrics_builder(id2label):
    seqeval = evaluate.load("seqeval")

    def compute_metrics(p):
        predictions, labels = p
        predictions = np.argmax(predictions, axis=2)

        # Remove ignored index (-100) and convert to string labels
        true_predictions = [
            [id2label[p_idx] for (p_idx, l_idx) in zip(prediction, label) if l_idx != -100]
            for prediction, label in zip(predictions, labels)
        ]
        true_labels = [
            [id2label[l_idx] for (p_idx, l_idx) in zip(prediction, label) if l_idx != -100]
            for prediction, label in zip(predictions, labels)
        ]

        results = seqeval.compute(predictions=true_predictions, references=true_labels)
        return {
            "precision": results["overall_precision"],
            "recall": results["overall_recall"],
            "f1": results["overall_f1"],
            "accuracy": results["overall_accuracy"],
        }
    return compute_metrics

def train_biobert(config_path="configs/config.yaml", force=False):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    set_seed(config["training"]["seed"])

    model_config = config["models"]["baseline"]
    model_name = model_config["name"]
    hf_id = model_config["hf_id"]
    save_dir = Path(model_config["save_dir"])

    if save_dir.exists() and (save_dir / "pytorch_model.bin").exists() and not force:
        print(f"Checkpoint already exists at {save_dir}. Skipping training (use --force to overwrite).")
        return save_dir

    if save_dir.exists() and (save_dir / "model.safetensors").exists() and not force:
        print(f"Checkpoint already exists at {save_dir}. Skipping training (use --force to overwrite).")
        return save_dir

    print(f"\n================ FINE-TUNING {model_name} ({hf_id}) ================")
    
    # Device detection
    device = "cuda" if torch.cuda.is_available() else "cpu"
    num_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    
    batch_size = config["training"]["batch_size"]
    print(f"Device: {device_name} (GPUs: {num_gpus})")
    print(f"Batch size: {batch_size}")
    print(f"Model HF ID: {hf_id}")

    # Load processed data
    processed_data_dir = Path(config["dataset"]["processed_dir"]) / "baseline"
    if not processed_data_dir.exists():
        print(f"ERROR: Processed data directory not found at {processed_data_dir}. Run convert_to_bio.py first.")
        sys.exit(1)

    print(f"Loading processed dataset from {processed_data_dir}")
    ds_dict = load_from_disk(processed_data_dir)
    train_dataset = ds_dict["train"]
    val_dataset = ds_dict["validation"]

    id2label = {int(k): v for k, v in config["labels"]["id2label"].items()}
    label2id = config["labels"]["label2id"]

    tokenizer = AutoTokenizer.from_pretrained(hf_id)
    model = AutoModelForTokenClassification.from_pretrained(
        hf_id,
        num_labels=len(id2label),
        id2label=id2label,
        label2id=label2id
    )

    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)

    steps_per_epoch = len(train_dataset) // batch_size
    total_training_steps = steps_per_epoch * config["training"]["epochs"]
    warmup_steps = int(config["training"]["warmup_ratio"] * total_training_steps)

    training_args = TrainingArguments(
        output_dir=str(save_dir / "checkpoints"),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=config["training"]["learning_rate"],
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=config["training"]["epochs"],
        weight_decay=config["training"]["weight_decay"],
        warmup_steps=warmup_steps,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=10,
        seed=config["training"]["seed"],
        report_to="none"
    )

    compute_metrics_fn = compute_metrics_builder(id2label)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics_fn,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=config["training"]["early_stopping_patience"])]
    )

    print("\nStarting model training...")
    trainer.train()

    print(f"\nSaving best trained model and tokenizer to: {save_dir}")
    save_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(save_dir))
    tokenizer.save_pretrained(str(save_dir))

    # Save label mappings and training metadata
    meta = {
        "model_name": model_name,
        "hf_id": hf_id,
        "id2label": id2label,
        "label2id": label2id,
        "training_config": config["training"]
    }
    with open(save_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Final evaluation on validation set
    eval_res = trainer.evaluate()
    print(f"\nValidation Results for {model_name}:")
    print(f"  Precision: {eval_res.get('eval_precision', 0):.4f}")
    print(f"  Recall:    {eval_res.get('eval_recall', 0):.4f}")
    print(f"  F1 Score:  {eval_res.get('eval_f1', 0):.4f}")

    with open(save_dir / "val_metrics.json", "w", encoding="utf-8") as f:
        json.dump(eval_res, f, indent=2)

    return save_dir

if __name__ == "__main__":
    train_biobert()
