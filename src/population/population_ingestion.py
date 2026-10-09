"""Ingest real population evidence for disease-associated genes (resumable, cache-backed).

    python -m src.population.population_ingestion --max-genes 400
Order of work: genes of the evaluation target diseases first (so that the ranking experiment has coverage),
then the remaining disease genes. The gnomAD API is rate limited (~10 queries/min), so ingestion is slow by
design; every gene is cached on disk and the run can be stopped/resumed at any time.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.append(os.path.abspath("."))
from src.population.gnomad_adapter import GnomadClient, cached_fetch  # noqa: E402

CACHE = Path("data/raw/gnomad/gene_cache")


def prioritized_genes(config_path="configs/config.yaml"):
    from src.evaluation.evaluate_retrieval import build_queries
    kb = json.load(open(Path("data/embeddings/records/disease_records.json"), encoding="utf-8"))
    genes_of = {d["disease_id"]: d["genes"] for d in kb}
    ordered, seen = [], set()
    test_q, _, _ = build_queries(config_path)
    val_q, _, _ = build_queries(config_path, seed=11, n_queries=300, exclude_ids={q["disease_id"] for q in test_q})
    for q in test_q + val_q:
        for g in genes_of.get(q["disease_id"], []):
            if g not in seen:
                seen.add(g); ordered.append(g)
    for d in kb:
        for g in d["genes"]:
            if g not in seen:
                seen.add(g); ordered.append(g)
    return ordered


def run(max_genes=None, config_path="configs/config.yaml"):
    CACHE.mkdir(parents=True, exist_ok=True)
    client = GnomadClient()
    genes = prioritized_genes(config_path)
    todo = [g for g in genes if not (CACHE / f"{g}.json").exists()]
    print(f"{len(genes)} disease genes, {len(genes) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    for i, g in enumerate(todo[:max_genes] if max_genes else todo, 1):
        try:
            rec = cached_fetch(client, g, CACHE)
            print(f"[{i}] {g}: {rec['status']} plp_with_counts={len(rec.get('plp_variants', []))}", flush=True)
        except Exception as e:  # noqa: BLE001 - recorded, run continues
            print(f"[{i}] {g}: ERROR {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-genes", type=int, default=None)
    run(ap.parse_args().max_genes)
