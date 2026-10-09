import os
import json
import yaml
import pandas as pd
from pathlib import Path

from src.population.variant_normalizer import VariantNormalizer

def process_indigen_data(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    indigen_raw_dir = Path(config["population"]["indigen_raw_dir"])
    raw_file = indigen_raw_dir / "indigen_variants_raw.csv"

    if not raw_file.exists():
        from src.population.inspect_population_data import generate_sample_raw_population_data
        generate_sample_raw_population_data(config_path)

    df_raw = pd.read_csv(raw_file)
    normalizer = VariantNormalizer()

    processed_rows = []
    for _, row in df_raw.iterrows():
        raw_id = row.get("Variant_ID", row.get("rsid", ""))
        chrom = row.get("Chromosome", row.get("chrom", ""))
        pos = row.get("Position", row.get("pos", ""))
        ref = row.get("Ref_Allele", row.get("ref", ""))
        alt = row.get("Alt_Allele", row.get("alt", ""))
        gene = row.get("Gene_Symbol", row.get("gene", "UNKNOWN"))

        norm_var = normalizer.normalize_variant(raw_id, chrom, pos, ref, alt, gene=gene, source="IndiGen")

        af = float(row.get("IndiGen_AF", row.get("AF", 0.0)))
        ac = int(row.get("IndiGen_AC", row.get("AC", 0)))
        an = int(row.get("IndiGen_AN", row.get("AN", 2058)))

        processed_rows.append({
            "variant_id": norm_var["normalized_identifier"],
            "raw_variant_id": norm_var["original_identifier"],
            "gene": str(gene).strip().upper(),
            "allele_frequency": round(af, 6),
            "allele_count": ac,
            "allele_number": an,
            "source": "IndiGen"
        })

    df_processed = pd.DataFrame(processed_rows)

    out_dir = Path(config["population"]["indigen_processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / config["population"]["indigen_file"]
    csv_path = out_dir / "indigen_frequency.csv"

    df_processed.to_csv(csv_path, index=False)
    try:
        df_processed.to_parquet(parquet_path, index=False)
        print(f"IndiGen Frequency Table processed -> saved Parquet to {parquet_path}")
    except Exception as e:
        print(f"Parquet save fallback to CSV ({e}) -> saved CSV to {csv_path}")

    print(f"Processed {len(df_processed)} IndiGen variant records across {df_processed['gene'].nunique()} unique genes.")
    return df_processed

if __name__ == "__main__":
    process_indigen_data()
