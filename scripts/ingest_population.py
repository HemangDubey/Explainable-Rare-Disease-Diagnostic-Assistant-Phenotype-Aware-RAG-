"""Phase 3R data completion: ClinVar P/LP (public) x gnomAD v4.1 exome VCF (public) -> per-gene population evidence.

    python scripts/ingest_population.py --clinvar     # parse ClinVar variant_summary.txt.gz -> parquet
    python scripts/ingest_population.py --estimate    # upper-bound bytes to read from gnomAD (index only, no data read)
    python scripts/ingest_population.py --run         # ingest all disease-associated genes (resumable)
    python scripts/ingest_population.py --crosscheck  # compare VCF-derived counts with the earlier gnomAD API records
    python scripts/ingest_population.py --genes SLC26A4,PAX8,TSHR      # targeted, idempotent (same service as the API)
    python scripts/ingest_population.py --from-cases                   # every candidate gene in stored cases (all users)
    python scripts/ingest_population.py --genes PAX8 --force           # re-fetch even if cached
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.append(os.path.abspath("."))
from src.population import clinvar_adapter, gnomad_bulk  # noqa: E402

PLP = Path("data/processed/population/clinvar_plp_grch38.parquet")
TOT = Path("data/processed/population/clinvar_gene_totals.json")
CACHE = Path("data/raw/gnomad/gene_cache")
API_CACHE = Path("data/raw/gnomad/gene_cache_api_validation")


def kb_genes():
    kb = json.load(open("data/embeddings/records/disease_records.json", encoding="utf-8"))
    return sorted({g for d in kb for g in d["genes"]})


def prioritized(genes):
    """Evaluation-target genes first (so partial runs are still useful), then the rest."""
    from src.evaluation.evaluate_retrieval import build_queries
    kb = {d["disease_id"]: d["genes"] for d in json.load(open("data/embeddings/records/disease_records.json", encoding="utf-8"))}
    test_q, _, _ = build_queries("configs/config.yaml")
    val_q, _, _ = build_queries("configs/config.yaml", seed=11, n_queries=300, exclude_ids={q["disease_id"] for q in test_q})
    order, seen = [], set()
    for q in test_q + val_q:
        for g in kb.get(q["disease_id"], []):
            if g not in seen:
                seen.add(g); order.append(g)
    return order + [g for g in genes if g not in seen]


def crosscheck():
    """Compare VCF-derived exome AC/AN/sas with the independent gnomAD API records for the same variants."""
    n = bad = 0
    worst = []
    for p in API_CACHE.glob("*.json"):
        api = json.load(open(p, encoding="utf-8"))
        mine_p = CACHE / p.name
        if api.get("status") != "available" or not mine_p.exists():
            continue
        mine = {v["variant_id"]: v for v in json.load(open(mine_p, encoding="utf-8")).get("plp_variants", [])}
        for v in api["plp_variants"]:
            m = mine.get(v["variant_id"])
            ex = v.get("exome")
            if m is None or not ex:
                continue
            n += 1
            same = (m["exome"]["ac"], m["exome"]["an"], m["exome"]["sas_ac"], m["exome"]["sas_an"]) == (ex["ac"], ex["an"], ex["sas_ac"], ex["sas_an"])
            if not same:
                bad += 1
                if len(worst) < 5:
                    worst.append({"variant": v["variant_id"], "api": ex, "vcf": m["exome"]})
    out = {"variants_compared": n, "mismatches": bad, "examples": worst}
    Path("reports").mkdir(exist_ok=True)
    json.dump(out, open("reports/population_crosscheck_vcf_vs_api.json", "w", encoding="utf-8"), indent=2)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for f in ("clinvar", "estimate", "run", "crosscheck"):
        ap.add_argument(f"--{f}", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-genes", type=int, default=None)
    ap.add_argument("--budget-gb", type=float, default=None, help="ingest genes in value-per-byte order until this index-estimated size")
    ap.add_argument("--genes", type=str, default=None, help="comma-separated gene symbols (aliases resolved via NCBI GeneID)")
    ap.add_argument("--from-cases", action="store_true", help="genes of the ranked candidates in every stored case")
    ap.add_argument("--force", action="store_true", help="re-fetch genes that are already cached")
    a = ap.parse_args()
    if a.genes or a.from_cases:
        from src.population.gene_evidence import GeneEvidenceService
        from src.population.population_lookup import PopulationLookup
        targets = [g.strip() for g in (a.genes or "").split(",") if g.strip()]
        if a.from_cases:
            from sqlalchemy import select
            from src.db.models import Case
            from src.db.session import session_scope
            with session_scope() as s:
                for data in s.scalars(select(Case.data)).all():
                    for c in (data or {}).get("fused_candidates") or []:
                        targets += [g for g in c.get("genes", []) if g not in targets]
        svc = GeneEvidenceService(PopulationLookup())
        summary = {}
        for g in targets:
            r = svc.ingest(g, force=a.force)
            summary[r["status"]] = summary.get(r["status"], 0) + 1
            print(f"{g}: {r['status']}" + (f" ({r.get('reason')})" if r.get("reason") else ""), flush=True)
        print(json.dumps({"genes": len(targets), "by_status": summary}))
    if a.clinvar:
        print(json.dumps(clinvar_adapter.build(Path("data/raw/clinvar/variant_summary.txt.gz"), PLP), indent=1))
    if a.estimate:
        est = gnomad_bulk.estimate_bytes(pd.read_parquet(PLP), kb_genes())
        print({k: v for k, v in est.items() if k != "per_gene"}, f"-> {est['total_bytes_upper_bound'] / 1e9:.2f} GB upper bound")
        top = sorted(est["per_gene"].items(), key=lambda x: -x[1])[:5]
        print("largest:", [(g, round(b / 1e6)) for g, b in top])
    if a.run:
        if a.budget_gb:
            pr = json.load(open("data/processed/population/ingest_priority.json"))["ordered"]
            genes = [r["gene"] for r in pr if r["cum_est_bytes"] <= a.budget_gb * 1e9]
            print(f"priority budget {a.budget_gb} GB -> {len(genes)} genes")
        else:
            genes = prioritized(kb_genes())
        if a.max_genes:
            genes = genes[:a.max_genes]
        print(gnomad_bulk.run(genes, PLP, TOT, CACHE, workers=a.workers))
    if a.crosscheck:
        print(json.dumps(crosscheck(), indent=1))
