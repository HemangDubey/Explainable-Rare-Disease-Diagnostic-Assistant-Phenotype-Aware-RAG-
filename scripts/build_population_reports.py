"""Write the Phase 3R population reports from REAL cached data (no values are typed in by hand).

    python scripts/build_population_reports.py [--api http://127.0.0.1:8000]
Outputs in reports/: population_data_provenance.json, population_frequency_summary.csv, population_matching_report.csv,
population_scoring_method.md, ranking_explanations.json. (ranking_*.* and population_coverage.json are written by
src/evaluation/evaluate_ranking.py; population_crosscheck_vcf_vs_api.json by scripts/ingest_population.py --crosscheck.)
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

import requests
import yaml

sys.path.append(os.path.abspath("."))
from src.population.population_lookup import PopulationLookup  # noqa: E402

CASE = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


def main(api):
    cfg = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))
    lk = PopulationLookup()
    cache = Path(cfg["population"]["gnomad_gene_cache_dir"])
    recs = [g["rec"] for g in lk.genes.values()]
    fetched = sorted(r["fetched_at"] for r in recs) or [None]
    avail = [r for r in recs if r["status"] == "available"]
    n_var = sum(len(r.get("plp_variants", [])) for r in recs)
    n_sas = sum(1 for r in recs for v in r.get("plp_variants", []) if (v.get("exome") or {}).get("sas_an"))
    n_nonpass = sum(r.get("non_pass_variants", 0) for r in recs)
    clin = json.load(open("data/processed/population/clinvar_provenance.json"))
    xcheck = json.load(open("reports/population_crosscheck_vcf_vs_api.json")) if Path("reports/population_crosscheck_vcf_vs_api.json").exists() else None

    clinvar = {
        "source": "ClinVar", "source_version": f"variant_summary.txt.gz, file last modified {clin['file_last_modified_utc']}",
        "access_mechanism": clin["url"], "genome_build": "GRCh38", "retrieval_date_utc": clin["processed_at"],
        "file": clin["file"], "file_bytes": clin["file_bytes"],
        "record_count": {"rows_in_file": clin["rows_in_file"], "rows_grch38": clin["rows_grch38"],
                         "plp_unique_variants_after_filters": clin["plp_unique_variants"], "genes_with_plp": clin["genes_with_plp"]},
        "filtering_rules": clin["filters"], "source_record_ids": "ClinVar VariationID and AlleleID preserved per variant",
        "processing_script": clin["processing_script"], "license_terms_status": clin["license_terms"],
        "derived": "Derived from real ClinVar records using the project's normalization/filtering pipeline.",
    }
    gnomad = {
        "source": "gnomAD", "source_version": "gnomAD v4.1 (release 4.1), EXOME callset, sites VCF",
        "access_mechanism": "public Google Cloud bucket, HTTP range requests through the tabix index: "
                            "https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/exomes/gnomad.exomes.v4.1.sites.<chr>.vcf.bgz "
                            "(no whole-file download; only blocks containing ClinVar P/LP variants were read)",
        "genome_build": "GRCh38", "retrieval_date_utc": {"first": fetched[0], "last": fetched[-1]},
        "fields_used": ["AC", "AN", "AC_sas", "AN_sas", "FILTER"],
        "populations": {"global": "all samples (AC/AN)", "south_asian": "gnomAD South Asian genetic-ancestry group (AC_sas/AN_sas)"},
        "record_count": {"genes_processed": len(recs), "genes_with_clinvar_plp_records": len(avail),
                         "clinvar_plp_variants_found_pass_in_gnomad_exomes": n_var, "of_which_with_south_asian_counts": n_sas,
                         "found_but_not_PASS_excluded": n_nonpass},
        "filtering_rules": {"variants": "ClinVar P/LP (see ClinVar entry) present in gnomAD exomes", "filter": "FILTER == PASS only",
                            "callset": "exomes only; genome-callset-only variants are not counted"},
        "source_record_ids": "variant identified by canonical chr:pos:ref:alt (GRCh38) joined to the ClinVar VariationID",
        "processing_script": ["src/population/gnomad_bulk.py", "src/population/remote_tabix.py", "scripts/ingest_population.py"],
        "license_terms_status": "Publicly accessible; subject to gnomAD terms of use (https://gnomad.broadinstitute.org/terms).",
        "validation": ("VCF-derived exome AC/AN and South-Asian AC/AN were compared with independent records from the public gnomAD API: "
                       f"{xcheck['variants_compared']} variants compared, {xcheck['mismatches']} mismatches" if xcheck else "cross-check not run"),
        "derived": "Derived from real source records using the project's normalization/filtering pipeline.",
        "coverage_note": "Genes were ingested in value-per-byte order under a download budget; see population_coverage.json for actual coverage.",
    }
    indigen = {
        "source": "IndiGen (CSIR-IGIB IndiGenomes)", "status": "UNAVAILABLE - ACCESS REQUIRED", "records": 0, "source_version": None,
        "access_mechanism": "https://clingen.igib.res.in/indigen (browse/search portal; account registration; research use only)",
        "reason": "No documented bulk allele-frequency download; sign-in requires account registration. No account was created, nothing was scraped or generated, "
                  "and no other dataset is labelled or substituted as IndiGen.",
        "next_step": "Request the variant allele-frequency export from CSIR-IGIB; place it in data/raw/indigen/ and run python src/population/indigen_adapter.py",
        "processing_script": "src/population/indigen_adapter.py (implemented, untested on real data)",
    }
    legacy = {"status": "QUARANTINED", "location": "data/processed/population/_legacy_synthetic/",
              "note": "Randomly generated development placeholders; not evidence; not used by any production code."}
    Path("reports").mkdir(exist_ok=True)
    json.dump({"datasets": [clinvar, gnomad, indigen], "legacy_synthetic_artifacts": legacy,
               "regional_comparator_note": "The regional comparator is 'gnomAD South Asian' (a genetic-ancestry group). It is NOT IndiGen and NOT Indian-specific.",
               "interpretation": "Gene-level cumulative P/LP allele frequency; population frequency is not a disease probability."},
              open("reports/population_data_provenance.json", "w", encoding="utf-8"), indent=2)

    with open("reports/population_frequency_summary.csv", "w", newline="", encoding="utf-8") as f, \
            open("reports/population_matching_report.csv", "w", newline="", encoding="utf-8") as m:
        w, mw = csv.writer(f), csv.writer(m)
        w.writerow(["gene", "status", "clinvar_records", "clinvar_plp", "plp_in_gnomad_pass", "caf_gnomad_global", "caf_gnomad_south_asian", "level", "dataset_version"])
        mw.writerow(["input_gene", "normalized_gene", "mapping_source", "mapping_status", "gnomad_status", "indigen_status"])
        for sym in sorted(lk.genes):
            s = lk.genes[sym]["sum"]; info = lk.lookup_gene(sym)
            w.writerow([sym, s["status"], s.get("clinvar_total"), s.get("clinvar_plp"), s.get("n_plp_with_counts"),
                        s.get("caf_global"), s.get("caf_sas"), "GENE_LEVEL", s["dataset_version"]])
            mw.writerow([sym, info["normalized_gene"], "ClinVar GeneSymbol (exact match, upper-cased)", info["mapping_status"],
                         info["gnomad"]["status"], info["indigen"]["status"]])

    r, p = cfg["ranking"], cfg["population"]
    Path("reports/population_scoring_method.md").write_text(f"""# Population Evidence Scoring Method (Phase 3R, final)

Population frequency is evidence about **how often pathogenic alleles occur in a population**. It is NOT a disease
probability and not a diagnosis; it can only modify candidate prioritisation by a small, configurable amount.

## Sources and labels (never merged)
* **gnomAD global** - all gnomAD v4.1 exome samples.  * **gnomAD South Asian** - gnomAD's South Asian genetic-ancestry group
(a regional comparator; **not IndiGen, not Indian-specific**).  * **IndiGen** - unavailable (access required).

## Statistic (gene level, explicitly `GENE_LEVEL`; built from variant-level records)
For gene g: `CAF_pop(g) = sum over ClinVar germline P/LP variants (>= {p['clinvar_min_gold_stars']} review star) found with FILTER=PASS in gnomAD exomes of AC_pop(v)/AN_pop(v)`,
pop in {{global, South Asian}}. `CAF = 0` is a real observation (no carrier seen); a gene with no P/LP variants has no statistic
(`not_found`); a gene not ingested is `unavailable`; a variant lacking South Asian counts is excluded from the South Asian sum only.
Disease statistic: `CAF_pop(D) = sum_g CAF_pop(g)` over its genes that have data. No pseudocounts are used anywhere.

## Signals (empirical CDFs over the ingested reference genes; undefined if fewer than {p['min_reference_genes']} reference genes)
* `s_sas(D)   = F_sas(CAF_sas(D))`, `F_sas(0) = 0`  (South Asian carrier-frequency rank)
* `s_glob(D)  = F_glob(CAF_global(D))`, `F_glob(0) = 0`
* `s_enr(D)   = F_enr(log2(CAF_sas(D) / CAF_global(D)))` - South-Asian-vs-global comparison; **defined only when both CAFs are > 0**
  (zero or missing frequencies give `null`, never 0, so 0/0 cannot occur). F_enr is the ECDF of the log2 ratio over genes where both are > 0.
Configurations: **B** uses `s_sas`; **C** uses the mean of `s_sas` and `s_enr` (those available); **E** (extra) uses `s_glob`; **D** (IndiGen) is blocked.

## Ranking (single authoritative configuration: `configs/config.yaml -> ranking`)
```
base_score  = w_phenotype * phenotype_score + w_retrieval * retrieval_score        (w_phenotype + w_retrieval = 1)
final_score = base_score + w_population * (population_signal - population_reference)   if a signal exists
            = base_score                                                                 otherwise
```
`phenotype_score` and `retrieval_score` are never modified by the population stage. Missing evidence contributes exactly 0 (no neutral placeholder).
`rank_change` = rank from `base_score` alone minus final rank (positive = promoted). Weights: see `best_ranking_weights.json`
(phenotype/retrieval frozen from validation search; w_population tuned on validation only when >= {p.get('min_candidate_coverage_for_tuning', 0.25):.0%}
of validation candidate slots carry a signal, otherwise set to 0 and reported).
""", encoding="utf-8")

    try:
        d = requests.post(f"{api}/api/rank", json={"clinical_text": CASE, "top_k": 5, "exp_config": "rag_south_asian_global"}, timeout=300).json()
        expl = [{"candidate": c["disease_name"], "disease_id": c["disease_id"], "retrieval_score": c["retrieval_score"],
                 "phenotype_score": c["phenotype_score"], "genes": c["associated_genes"],
                 "population": {k: v for k, v in c["population"].items() if k != "genes"},
                 "population_signal": c["population"]["signal"], "population_contribution": c["population_contribution"],
                 "final_score": c["final_score"], "rank": c["rank"], "baseline_rank": c["baseline_rank"], "rank_change": c["rank_change"]}
                for c in d["ranked_candidates"]]
        json.dump({"input": "synthetic example sentence (no patient data)", "population_coverage": d["population_coverage"],
                   "candidates": expl, "text_explanations": d["ranking_explanations"]},
                  open("reports/ranking_explanations.json", "w", encoding="utf-8"), indent=2)
    except requests.RequestException as e:
        print("API not reachable; ranking_explanations.json not written:", type(e).__name__)
    print("reports written; genes in cache:", len(recs))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8000")
    main(ap.parse_args().api)
