import os
import json
import yaml
import numpy as np
import pandas as pd
from pathlib import Path

from src.population.indigen_processor import process_indigen_data
from src.population.gnomad_processor import process_gnomad_data

def compare_frequencies(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ind_path = Path(config["population"]["indigen_processed_dir"]) / config["population"]["indigen_file"]
    gno_path = Path(config["population"]["gnomad_processed_dir"]) / config["population"]["gnomad_file"]

    if not ind_path.exists():
        df_ind = process_indigen_data(config_path)
    else:
        try: df_ind = pd.read_parquet(ind_path)
        except Exception: df_ind = pd.read_csv(Path(config["population"]["indigen_processed_dir"]) / "indigen_frequency.csv")

    if not gno_path.exists():
        df_gno = process_gnomad_data(config_path)
    else:
        try: df_gno = pd.read_parquet(gno_path)
        except Exception: df_gno = pd.read_csv(Path(config["population"]["gnomad_processed_dir"]) / "gnomad_frequency.csv")

    df_merged = pd.merge(df_ind, df_gno, on=["variant_id", "gene"], how="inner", suffixes=("_indigen", "_gnomad"))

    eps = 1e-7
    comparison_rows = []

    for _, r in df_merged.iterrows():
        ind_af = float(r["allele_frequency"])
        gno_af = float(r["global_af"])
        sas_af = float(r["south_asian_af"])

        af_ratio = round((ind_af + eps) / (gno_af + eps), 4)
        af_enrichment = round((ind_af - gno_af) / (gno_af + eps), 4)

        comparison_rows.append({
            "variant_id": r["variant_id"],
            "gene": r["gene"],
            "indigen_af": ind_af,
            "gnomad_global_af": gno_af,
            "gnomad_south_asian_af": sas_af,
            "indian_global_af_ratio": af_ratio,
            "indian_af_enrichment": af_enrichment
        })

    df_comp = pd.DataFrame(comparison_rows)

    reports_dir = Path(config["dataset"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_csv = reports_dir / "population_frequency_summary.csv"
    df_comp.to_csv(out_csv, index=False)

    print(f"Population Frequency Comparison generated -> saved {len(df_comp)} matched variants to {out_csv}")
    return df_comp

if __name__ == "__main__":
    compare_frequencies()
