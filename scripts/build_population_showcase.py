"""Builds frontend/public/data/population_showcase.json: the landing page's population-frequency example, derived ONLY from the
project's real ClinVar x gnomAD v4.1 per-gene cache (data/raw/gnomad/gene_cache). It replaces hand-typed example numbers.

For each gene the shown variant is the ClinVar P/LP variant with the most review stars, then the most gnomAD exome alleles observed.
Global and South Asian frequencies are reported separately; IndiGen is reported as unavailable unless an authorised export has been
ingested (it is then read through the same PopulationLookup the ranking uses). Nothing is estimated or filled in.

    python scripts/build_population_showcase.py
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath("."))
from src.population.population_lookup import PopulationLookup  # noqa: E402

GENES = ["GJB2", "HFE", "HBB", "SLC25A20"]          # well-known recessive-disease genes present in the cache; examples only
OUT = "frontend/public/data/population_showcase.json"


def pick_variant(rec):
    best = None
    for v in rec.get("plp_variants", []):
        ex = v.get("exome") or {}
        if not ex.get("an") or not ex.get("sas_an"):
            continue
        key = (v.get("gold_stars") or 0, ex.get("ac") or 0)
        if best is None or key > best[0]:
            best = (key, v)
    return best[1] if best else None


def main():
    lk = PopulationLookup()
    rows = []
    for g in GENES:
        entry = lk.genes.get(g)
        if not entry or entry["rec"].get("status") != "available":
            rows.append({"gene": g, "status": "unavailable", "reason": "gene not in the ClinVar/gnomAD cache"})
            continue
        rec = entry["rec"]
        v = pick_variant(rec)
        if v is None:
            rows.append({"gene": g, "status": "not_found", "reason": "no P/LP variant with gnomAD global and South Asian allele numbers"})
            continue
        ex = v["exome"]
        af_g, af_s = ex["ac"] / ex["an"], ex["sas_ac"] / ex["sas_an"]
        ind = lk.lookup_gene(g)["indigen"]
        iv = lk.indigen.lookup_variant(v["variant_id"]) if lk.indigen.available else {"status": "unavailable"}
        rows.append({
            "gene": g, "status": "available", "variant_id": v["variant_id"], "clinvar_variation_id": v.get("clinvar_variation_id"),
            "clinical_significance": v.get("clinical_significance"), "review_status": v.get("review_status"), "gold_stars": v.get("gold_stars"),
            "gnomad_global": {"af": af_g, "ac": ex["ac"], "an": ex["an"]},
            "gnomad_south_asian": {"af": af_s, "ac": ex["sas_ac"], "an": ex["sas_an"]},
            "log2_sas_vs_global": math.log2(af_s / af_g) if af_s > 0 and af_g > 0 else None,
            "indigen": ({"status": "available", "af": iv.get("allele_frequency"), "dataset": iv.get("dataset_version")}
                        if iv.get("status") == "available" else
                        {"status": iv.get("status", "unavailable"), "reason": ind.get("reason") or "variant not in the IndiGen export"}),
            "dataset": rec.get("dataset"), "reference_genome": rec.get("reference_genome"), "fetched_at": rec.get("fetched_at"),
        })
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "generator": "scripts/build_population_showcase.py",
        "sources": {"clinvar": "ClinVar variant_summary (GRCh38, germline P/LP, >=1 review star)",
                    "gnomad": "gnomAD v4.1 exomes (global and South Asian ancestry group)",
                    "indigen": "available" if lk.indigen.available else "unavailable - access required (CSIR-IGIB); nothing substituted"},
        "note": "Reference allele frequencies of known pathogenic variants; examples only, not patient data. gnomAD South Asian is not India-specific.",
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT}: " + ", ".join(f"{r['gene']}={r['status']}" for r in rows))


if __name__ == "__main__":
    main()
