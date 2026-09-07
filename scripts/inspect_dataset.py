import os
import json
import yaml
import pandas as pd
from pathlib import Path

def inspect_dataset(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    raw_dir = Path(config["dataset"]["raw_dir"])
    train_path = raw_dir / config["dataset"]["train_file"]
    dev_path = raw_dir / config["dataset"]["dev_file"]
    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading Train dataset: {train_path}")
    df_train = pd.read_csv(train_path, sep="\t", dtype=str)
    print(f"Reading Dev dataset: {dev_path}")
    df_dev = pd.read_csv(dev_path, sep="\t", dtype=str)

    # Combine for global stats analysis
    df_all = pd.concat([df_train, df_dev], ignore_index=True)

    def analyze_df(df, name):
        num_rows = len(df)
        num_obs = df["StringID"].nunique()
        hpo_terms = df["Term"].dropna().unique()
        hpo_terms_valid = [t for t in hpo_terms if t != "NA"]
        
        annotated_rows = df[df["Spans"].notna() & (df["Spans"] != "NA")]
        num_annotations = len(annotated_rows)
        
        pos_annotations = df[(df["Spans"].notna()) & (df["Spans"] != "NA") & ((df["Negated"].isna()) | (df["Negated"] == "NA"))]
        neg_annotations = df[(df["Spans"].notna()) & (df["Spans"] != "NA") & (df["Negated"] == "X")]
        
        decoy_rows = df[(df["Spans"].isna()) | (df["Spans"] == "NA") | (df["Term"] == "NA")]
        num_decoys = len(decoy_rows)

        # Offset analysis
        discontinuous_count = 0
        continuous_count = 0
        for span_str in annotated_rows["Spans"]:
            if "," in str(span_str):
                discontinuous_count += 1
            else:
                continuous_count += 1

        return {
            "name": name,
            "total_rows": num_rows,
            "unique_observations": num_obs,
            "total_annotations": num_annotations,
            "unique_hpo_ids": len(hpo_terms_valid),
            "positive_annotations": len(pos_annotations),
            "negated_annotations": len(neg_annotations),
            "decoy_or_na_rows": num_decoys,
            "continuous_spans": continuous_count,
            "discontinuous_spans": discontinuous_count,
        }

    train_stats = analyze_df(df_train, "Train")
    dev_stats = analyze_df(df_dev, "Dev")
    overall_stats = analyze_df(df_all, "Overall")

    print("\n================ DATASET INSPECTION REPORT ================")
    print(f"Columns present: {list(df_all.columns)}")
    print(f"\n--- OVERALL STATISTICS ---")
    print(f"Total rows in dataset: {overall_stats['total_rows']}")
    print(f"Total unique observations: {overall_stats['unique_observations']}")
    print(f"Total phenotype annotations (with spans): {overall_stats['total_annotations']}")
    print(f"Total unique HPO IDs: {overall_stats['unique_hpo_ids']}")
    print(f"Positive phenotype mentions (Negated=NA): {overall_stats['positive_annotations']}")
    print(f"Negated phenotype mentions (Negated=X): {overall_stats['negated_annotations']}")
    print(f"Decoy / NA observation rows: {overall_stats['decoy_or_na_rows']}")
    print(f"Single continuous spans: {overall_stats['continuous_spans']}")
    print(f"Discontinuous / multi-segment spans: {overall_stats['discontinuous_spans']}")

    print(f"\n--- TRAIN SPLIT STATISTICS ---")
    print(f"Train Rows: {train_stats['total_rows']} | Unique Observations: {train_stats['unique_observations']}")
    print(f"Train Annotations: {train_stats['total_annotations']} | Unique HPO IDs: {train_stats['unique_hpo_ids']}")

    print(f"\n--- DEV SPLIT STATISTICS ---")
    print(f"Dev Rows: {dev_stats['total_rows']} | Unique Observations: {dev_stats['unique_observations']}")
    print(f"Dev Annotations: {dev_stats['total_annotations']} | Unique HPO IDs: {dev_stats['unique_hpo_ids']}")

    # Raw annotation samples
    print(f"\n--- RAW ANNOTATION SAMPLES ---")
    sample_rows = df_train.dropna(subset=["Spans"]).head(5)
    samples = []
    for idx, row in sample_rows.iterrows():
        text = str(row["Text"])
        spans_str = str(row["Spans"])
        extracted_spans = []
        if spans_str != "NA":
            for part in spans_str.split(","):
                part = part.strip()
                if "-" in part:
                    s, e = map(int, part.split("-"))
                    extracted_spans.append(text[s:e])
        sample_item = {
            "StringID": row["StringID"],
            "Text": text,
            "HPO_Term": row["Term"],
            "Negated": row["Negated"],
            "Spans": spans_str,
            "Extracted_Substrings": extracted_spans
        }
        samples.append(sample_item)
        print(f"\nSample {idx+1}:")
        print(f"  StringID: {sample_item['StringID']}")
        print(f"  Text: {sample_item['Text']}")
        print(f"  HPO Term: {sample_item['HPO_Term']} | Negated: {sample_item['Negated']}")
        print(f"  Spans: {sample_item['Spans']} -> {sample_item['Extracted_Substrings']}")

    inspection_data = {
        "train_stats": train_stats,
        "dev_stats": dev_stats,
        "overall_stats": overall_stats,
        "samples": samples
    }

    out_file = reports_dir / "dataset_inspection_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(inspection_data, f, indent=2)

    print(f"\nInspection report saved to: {out_file}")
    return inspection_data

if __name__ == "__main__":
    inspect_dataset()
