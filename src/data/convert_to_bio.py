import os
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from transformers import AutoTokenizer
from datasets import Dataset, DatasetDict

def parse_spans(span_str, text_len):
    """
    Parses span string like '7-25' or '0-4,79-89' into list of (start, end) tuples.
    Validates range against text length.
    """
    if pd.isna(span_str) or str(span_str).strip() in ["NA", "nan", ""]:
        return []
    
    segments = []
    for part in str(span_str).split(","):
        part = part.strip()
        if "-" in part:
            try:
                s_str, e_str = part.split("-")
                s, e = int(s_str), int(e_str)
                if 0 <= s < e <= text_len + 5: # allow small buffer for trailing whitespace
                    e = min(e, text_len)
                    segments.append((s, e))
            except ValueError:
                continue
    return segments

def process_observations_to_bio(df, tokenizer, max_length=512):
    """
    Groups observations by StringID, extracts text, merges all span segments,
    and aligns with tokenizer offsets mapping.
    """
    # Group by StringID
    grouped = df.groupby("StringID")
    
    data_items = []
    
    total_annotations_count = 0
    bio_compatible_annotations_count = 0
    overlapping_annotations_count = 0
    discontinuous_annotations_count = 0
    truncated_annotations_count = 0

    for string_id, group in grouped:
        text = str(group["Text"].iloc[0])
        text_len = len(text)
        
        obs_segments = [] # List of all (start, end) span segments for this observation
        obs_raw_spans = []
        
        for _, row in group.iterrows():
            span_str = str(row["Spans"])
            if span_str != "NA" and pd.notna(row["Spans"]):
                total_annotations_count += 1
                raw_segs = parse_spans(span_str, text_len)
                if raw_segs:
                    bio_compatible_annotations_count += 1
                    if "," in span_str:
                        discontinuous_annotations_count += 1
                    obs_raw_spans.append(span_str)
                    obs_segments.extend(raw_segs)

        # Check overlapping spans
        # Check if any character is covered by more than 1 span segment
        char_coverage = np.zeros(text_len, dtype=int)
        for s, e in obs_segments:
            char_coverage[s:e] += 1
        if np.any(char_coverage > 1):
            overlapping_annotations_count += 1

        # Tokenize with offsets
        encoding = tokenizer(
            text,
            max_length=max_length,
            padding=False,
            truncation=True,
            return_offsets_mapping=True
        )
        
        input_ids = encoding["input_ids"]
        attention_mask = encoding["attention_mask"]
        offset_mapping = encoding["offset_mapping"]

        # Generate BIO labels
        labels = []
        
        # Track which tokens belong to which segment
        for idx, (tok_start, tok_end) in enumerate(offset_mapping):
            # Special tokens ([CLS], [SEP], [PAD]) have offset (0, 0)
            if tok_start == tok_end:
                labels.append(-100)
                continue
            
            # Check truncation
            if tok_end > text_len:
                truncated_annotations_count += 1

            # Determine label for token
            # Label rules:
            # 1 (B-PHENOTYPE) if token start matches segment start or is first token of a segment
            # 2 (I-PHENOTYPE) if token is inside segment after first token
            # 0 (O) otherwise
            
            token_label = 0 # default O
            
            for s_start, s_end in obs_segments:
                # Token overlaps segment if tok_start < s_end and tok_end > s_start
                if tok_start < s_end and tok_end > s_start:
                    # Is this token the first token for this segment?
                    # It's first token if tok_start <= s_start or no previous token overlapped s_start
                    is_first_token = False
                    if tok_start <= s_start or (idx > 0 and offset_mapping[idx-1][1] <= s_start):
                        is_first_token = True
                    
                    if is_first_token:
                        token_label = 1 # B-PHENOTYPE takes highest priority
                        break
                    else:
                        if token_label != 1:
                            token_label = 2 # I-PHENOTYPE
            
            labels.append(token_label)

        data_items.append({
            "string_id": string_id,
            "text": text,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
            "raw_spans": json.dumps(obs_raw_spans)
        })

    report_metrics = {
        "total_annotations": total_annotations_count,
        "bio_compatible_annotations": bio_compatible_annotations_count,
        "overlapping_annotations": overlapping_annotations_count,
        "discontinuous_annotations": discontinuous_annotations_count,
        "truncated_annotations": truncated_annotations_count,
    }
    
    return data_items, report_metrics

def convert_dataset_to_bio(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    raw_dir = Path(config["dataset"]["raw_dir"])
    train_path = raw_dir / config["dataset"]["train_file"]
    dev_path = raw_dir / config["dataset"]["dev_file"]
    processed_dir = Path(config["dataset"]["processed_dir"])
    reports_dir = Path(config["dataset"]["reports_dir"])

    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    df_train = pd.read_csv(train_path, sep="\t", dtype=str)
    df_dev = pd.read_csv(dev_path, sep="\t", dtype=str)

    # Split Dev deterministically into Validation (50%) and Test (50%) by StringID
    unique_dev_ids = df_dev["StringID"].unique()
    np.random.seed(config["training"]["seed"])
    shuffled_dev_ids = unique_dev_ids.copy()
    np.random.shuffle(shuffled_dev_ids)

    mid = len(shuffled_dev_ids) // 2
    val_ids = set(shuffled_dev_ids[:mid])
    test_ids = set(shuffled_dev_ids[mid:])

    df_val = df_dev[df_dev["StringID"].isin(val_ids)].reset_index(drop=True)
    df_test = df_dev[df_dev["StringID"].isin(test_ids)].reset_index(drop=True)

    print(f"Data Splits Created:")
    print(f"  Train: {df_train['StringID'].nunique()} unique observations, {len(df_train)} rows")
    print(f"  Validation: {df_val['StringID'].nunique()} unique observations, {len(df_val)} rows")
    print(f"  Test: {df_test['StringID'].nunique()} unique observations, {len(df_test)} rows")

    models_config = config["models"]
    
    preprocessing_reports = {}

    for model_key in ["primary", "baseline"]:
        model_info = models_config[model_key]
        model_name = model_info["name"]
        hf_id = model_info["hf_id"]
        
        print(f"\nProcessing BIO conversion for model: {model_name} ({hf_id})")
        tokenizer = AutoTokenizer.from_pretrained(hf_id)

        train_data, train_report = process_observations_to_bio(df_train, tokenizer, config["training"]["max_length"])
        val_data, val_report = process_observations_to_bio(df_val, tokenizer, config["training"]["max_length"])
        test_data, test_report = process_observations_to_bio(df_test, tokenizer, config["training"]["max_length"])

        model_processed_dir = processed_dir / model_key
        model_processed_dir.mkdir(parents=True, exist_ok=True)

        # Convert to HF DatasetDict
        ds_dict = DatasetDict({
            "train": Dataset.from_pandas(pd.DataFrame(train_data)),
            "validation": Dataset.from_pandas(pd.DataFrame(val_data)),
            "test": Dataset.from_pandas(pd.DataFrame(test_data)),
        })
        
        ds_dict.save_to_disk(model_processed_dir)
        print(f"Saved processed dataset for {model_name} to: {model_processed_dir}")

        total_rep = {
            "model_name": model_name,
            "hf_id": hf_id,
            "total_annotations": train_report["total_annotations"] + val_report["total_annotations"] + test_report["total_annotations"],
            "bio_compatible_annotations": train_report["bio_compatible_annotations"] + val_report["bio_compatible_annotations"] + test_report["bio_compatible_annotations"],
            "overlapping_annotations": train_report["overlapping_annotations"] + val_report["overlapping_annotations"] + test_report["overlapping_annotations"],
            "discontinuous_annotations": train_report["discontinuous_annotations"] + val_report["discontinuous_annotations"] + test_report["discontinuous_annotations"],
            "truncated_annotations": train_report["truncated_annotations"] + val_report["truncated_annotations"] + test_report["truncated_annotations"],
            "handling_notes": "Continuous segments are converted to B/I tags using offset_mapping. Discontinuous spans are split into constituent segments and tagged sequentially. Overlapping spans resolve to B-PHENOTYPE at segment boundaries and I-PHENOTYPE inside. Original character spans preserved in raw_spans column."
        }
        preprocessing_reports[model_key] = total_rep

    # Save preprocessing report
    report_json_path = reports_dir / "preprocessing_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(preprocessing_reports, f, indent=2)

    report_txt_path = reports_dir / "preprocessing_report.txt"
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write("=== PREPROCESSING & BIO CONVERSION REPORT ===\n\n")
        for key, rep in preprocessing_reports.items():
            f.write(f"Model: {rep['model_name']} ({rep['hf_id']})\n")
            f.write(f"  Total Annotations: {rep['total_annotations']}\n")
            f.write(f"  BIO-Compatible Annotations: {rep['bio_compatible_annotations']}\n")
            f.write(f"  Overlapping Annotations: {rep['overlapping_annotations']}\n")
            f.write(f"  Discontinuous Annotations: {rep['discontinuous_annotations']}\n")
            f.write(f"  Truncated Annotations: {rep['truncated_annotations']}\n")
            f.write(f"  Handling Notes: {rep['handling_notes']}\n\n")

    print(f"\nPreprocessing reports generated at:\n  {report_json_path}\n  {report_txt_path}")
    return preprocessing_reports

if __name__ == "__main__":
    convert_dataset_to_bio()
