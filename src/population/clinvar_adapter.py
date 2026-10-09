"""ClinVar (NCBI, public) pathogenic / likely-pathogenic variants on GRCh38, from variant_summary.txt.gz.

Source: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz (public, no login).
Filters (also written to the provenance report): Assembly == GRCh38; germline origin; ClinicalSignificance exactly
Pathogenic / Likely pathogenic / Pathogenic/Likely pathogenic; review status >= min_gold_stars; simple ACGT
REF/ALT with a VCF-style position. Original identifiers (VariationID, AlleleID) are preserved.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.population.variant_normalizer import normalize_variant

SIGNIFICANCE = {"Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic"}
STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, single submitter": 1,
    "criteria provided, conflicting classifications": 1,
    "criteria provided, conflicting interpretations": 1,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    "no classification for the individual variant": 0,
}
USECOLS = ["#AlleleID", "Type", "GeneSymbol", "HGNC_ID", "ClinicalSignificance", "OriginSimple", "Assembly", "Chromosome",
           "ReviewStatus", "VariationID", "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF"]


def _stars(status) -> int:
    s = str(status).strip().lower()
    return STARS.get(s, 0)


def build(src: Path, out: Path, min_gold_stars=1) -> dict:
    df = pd.read_csv(src, sep="\t", usecols=USECOLS, dtype=str, compression="gzip", low_memory=False)
    total_rows = len(df)
    df = df[df["Assembly"] == "GRCh38"]
    n_grch38 = len(df)
    per_gene_total = {}
    exploded = df["GeneSymbol"].dropna().str.split(";").explode().str.strip()
    for g, n in exploded.value_counts().items():
        per_gene_total[g] = int(n)
    df = df[df["OriginSimple"].fillna("").str.contains("germline", case=False)]
    df = df[df["ClinicalSignificance"].isin(SIGNIFICANCE)].copy()
    df["gold_stars"] = df["ReviewStatus"].map(_stars)
    df = df[df["gold_stars"] >= min_gold_stars].copy()
    df["variant_id"] = [normalize_variant(c, p, r, a) for c, p, r, a in
                        zip(df["Chromosome"], df["PositionVCF"], df["ReferenceAlleleVCF"], df["AlternateAlleleVCF"])]
    df = df[df["variant_id"].notna()].copy()
    df["gene"] = df["GeneSymbol"].fillna("").str.split(";")
    df = df.explode("gene")
    df["gene"] = df["gene"].str.strip()
    df = df[df["gene"] != ""]
    df = df.rename(columns={"ClinicalSignificance": "clinical_significance", "ReviewStatus": "review_status",
                            "VariationID": "variation_id", "#AlleleID": "allele_id", "HGNC_ID": "hgnc_id"})
    keep = ["variant_id", "gene", "hgnc_id", "clinical_significance", "review_status", "gold_stars", "variation_id", "allele_id", "Type"]
    df = df[keep].drop_duplicates(["variant_id", "gene"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    prov = {
        "source": "ClinVar variant_summary.txt.gz",
        "url": "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz",
        "file": src.name, "file_bytes": src.stat().st_size,
        "file_last_modified_utc": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "rows_in_file": total_rows, "rows_grch38": n_grch38,
        "plp_variant_gene_records": len(df), "plp_unique_variants": int(df["variant_id"].nunique()),
        "genes_with_plp": int(df["gene"].nunique()),
        "filters": {"assembly": "GRCh38", "origin": "germline", "significance": sorted(SIGNIFICANCE),
                    "min_gold_stars": min_gold_stars, "alleles": "simple ACGT with VCF-style position"},
        "license_terms": "NCBI public domain data; see https://www.ncbi.nlm.nih.gov/home/about/policies/",
        "processing_script": "src/population/clinvar_adapter.py",
        "note": "Derived from real ClinVar records using the project's normalization/filtering pipeline.",
    }
    (out.parent / "clinvar_provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    (out.parent / "clinvar_gene_totals.json").write_text(json.dumps(per_gene_total), encoding="utf-8")
    return prov


if __name__ == "__main__":
    print(json.dumps(build(Path("data/raw/clinvar/variant_summary.txt.gz"),
                           Path("data/processed/population/clinvar_plp_grch38.parquet")), indent=1))
