import os
import json
import yaml
import pandas as pd
from pathlib import Path

from src.population.variant_normalizer import VariantNormalizer

def process_gnomad_data(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    gnomad_raw_dir = Path(config["population"]["gnomad_raw_dir"])
    raw_file = gnomad_raw_dir / "gnomad_variants_raw.csv"

    if not raw_file.exists():
        from src.population.inspect_population_data import generate_sample_raw_population_data
        generate_sample_raw_population_data(config_path)

    df_raw = pd.read_csv(raw_file)
    normalizer = VariantNormalizer()

    processed_rows = []
    for _, row in df_raw.iterrows():
        raw_id = row.get("rsid", row.get("Variant_ID", ""))
        chrom = row.get("chrom", row.get("Chromosome", ""))
        pos = row.get("pos", row.get("Position", ""))
        ref = row.get("ref", row.get("Ref_Allele", ""))
        alt = row.get("alt", row.get("Alt_Allele", ""))
        gene = row.get("gene_name", row.get("gene", "UNKNOWN"))

        norm_var = normalizer.normalize_variant(raw_id, chrom, pos, ref, alt, gene=gene, source="gnomAD")

        global_af = float(row.get("AF_global", row.get("AF", 0.0)))
        sas_af = float(row.get("AF_sas", row.get("AF_SAS", global_af)))

        processed_rows.append({
            "variant_id": norm_var["normalized_identifier"],
            "raw_variant_id": norm_var["original_identifier"],
            "gene": str(gene).strip().upper(),
            "global_af": round(global_af, 6),
            "south_asian_af": round(sas_af, 6),
            "source": "gnomAD_v3.1"
        })

    df_processed = pd.DataFrame(processed_rows)

    out_dir = Path(config["population"]["gnomad_processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / config["population"]["gnomad_file"]
    csv_path = out_dir / "gnomad_frequency.csv"

    df_processed.to_csv(csv_path, index=False)
    try:
        df_processed.to_parquet(parquet_path, index=False)
        print(f"gnomAD Frequency Table processed -> saved Parquet to {parquet_path}")
    except Exception as e:
        print(f"Parquet save fallback to CSV ({e}) -> saved CSV to {csv_path}")

    print(f"Processed {len(df_processed)} gnomAD variant records across {df_processed['gene'].nunique()} unique genes.")
    return df_processed

if __name__ == "__main__":
    process_gnomad_data()
