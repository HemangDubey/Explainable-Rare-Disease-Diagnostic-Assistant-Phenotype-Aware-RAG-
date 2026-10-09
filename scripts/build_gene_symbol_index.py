"""Builds data/processed/population/gene_symbol_index.json: a sourced gene-symbol resolver for the genomic evidence service.

Sources (both already in the project, no network):
  * ClinVar variant_summary.txt.gz  -> NCBI GeneID -> the GeneSymbol ClinVar uses for that gene (GRCh38 rows, single-gene records)
  * HPO phenotype_to_genes.txt      -> the knowledge base's gene symbol -> NCBI GeneID

A knowledge-base symbol that ClinVar spells differently (renamed / alias) is resolved through the shared NCBI GeneID, never by fuzzy
string matching. Idempotent: re-running overwrites the file with the same content for the same inputs.

    python scripts/build_gene_symbol_index.py
"""
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CLINVAR = Path("data/raw/clinvar/variant_summary.txt.gz")
P2G = Path("data/raw/disease/phenotype_to_genes.txt")
OUT = Path("data/processed/population/gene_symbol_index.json")


def main():
    by_id = defaultdict(Counter)
    for chunk in pd.read_csv(CLINVAR, sep="\t", usecols=["GeneID", "GeneSymbol", "Assembly"], dtype=str, chunksize=500_000):
        chunk = chunk[(chunk["Assembly"] == "GRCh38") & chunk["GeneID"].notna() & chunk["GeneSymbol"].notna()]
        chunk = chunk[~chunk["GeneSymbol"].str.contains(";", regex=False) & (chunk["GeneID"] != "-1")]
        for (gid, sym), n in chunk.groupby(["GeneID", "GeneSymbol"]).size().items():
            by_id[gid][sym] += int(n)
    clinvar_by_gene_id = {gid: c.most_common(1)[0][0] for gid, c in by_id.items()}

    hpo_symbol_to_gene_id = {}
    with open(P2G, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            hpo_symbol_to_gene_id.setdefault(row["gene_symbol"].strip().upper(), row["ncbi_gene_id"].strip())

    out = {
        "built_at": datetime.now(timezone.utc).isoformat(), "builder": "scripts/build_gene_symbol_index.py",
        "sources": {"clinvar": f"{CLINVAR} (modified {datetime.fromtimestamp(os.path.getmtime(CLINVAR), timezone.utc).isoformat()})",
                    "hpo": str(P2G)},
        "clinvar_by_gene_id": clinvar_by_gene_id,
        "hpo_symbol_to_gene_id": hpo_symbol_to_gene_id,
    }
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"wrote {OUT}: {len(clinvar_by_gene_id)} ClinVar gene ids, {len(hpo_symbol_to_gene_id)} HPO gene symbols")


if __name__ == "__main__":
    main()
