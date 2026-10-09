"""Choose which disease genes to ingest first under a byte budget (value per byte).

value(gene) = number of evaluation candidate slots (validation + test, Phase 2R top-50 pools) of diseases that
have this gene, each disease's slots split across its genes; cost(gene) = tabix-index estimate of compressed bytes.
Writes data/processed/population/ingest_priority.json (ordered gene list with value/cost). No data is read from gnomAD
here except the tiny index files.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.append(os.path.abspath("."))
from src.evaluation.evaluate_retrieval import build_queries  # noqa: E402
from src.population import gnomad_bulk  # noqa: E402
from src.retrieval.disease_retriever import DiseaseRetriever  # noqa: E402
from src.retrieval.store import get_store  # noqa: E402

CFG = "configs/config.yaml"


def main():
    test_q, _, _ = build_queries(CFG)
    val_q, _, _ = build_queries(CFG, seed=11, n_queries=300, exclude_ids={q["disease_id"] for q in test_q})
    retr = DiseaseRetriever("primary", CFG, store=get_store("primary", CFG))
    slots = Counter()
    for qs in (val_q, test_q):
        for q in qs:
            for c in retr.retrieve_diseases(q["names"], input_hpo_ids=q["hpo_ids"], top_k=50):
                slots[c["disease_id"]] += 1
    kb = {d["disease_id"]: d["genes"] for d in json.load(open("data/embeddings/records/disease_records.json", encoding="utf-8"))}
    value = Counter()
    for d, n in slots.items():
        genes = kb.get(d, [])
        for g in genes:
            value[g] += n / len(genes)
    plp = pd.read_parquet("data/processed/population/clinvar_plp_grch38.parquet")
    est = gnomad_bulk.estimate_bytes(plp, list(value))["per_gene"]
    rows = []
    for g, v in value.items():
        cost = est.get(g)
        if cost:
            rows.append({"gene": g, "value": v, "est_bytes": cost, "ratio": v / cost})
    rows.sort(key=lambda r: -r["ratio"])
    cum = 0
    for r in rows:
        cum += r["est_bytes"]; r["cum_est_bytes"] = cum
    out = {"distinct_candidate_diseases": len(slots), "total_slots": sum(slots.values()), "genes_with_value": len(value),
           "genes_with_clinvar_plp_cost": len(rows), "ordered": rows}
    Path("data/processed/population").mkdir(parents=True, exist_ok=True)
    json.dump(out, open("data/processed/population/ingest_priority.json", "w"))
    tot = sum(r["value"] for r in rows)
    for gb in (4, 8, 12, 20, 30):
        sel = [r for r in rows if r["cum_est_bytes"] <= gb * 1e9]
        print(f"budget {gb:2d} GB (index estimate): {len(sel):5d} genes, {100 * sum(r['value'] for r in sel) / tot:5.1f}% of candidate-slot value")


if __name__ == "__main__":
    main()
