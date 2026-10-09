"""Retrieval evaluation with a defensible (and honestly limited) protocol.

PROTOCOL - simulated patients from HPO annotations (standard in phenotype-driven diagnosis work):
  * Target diseases: a seeded random sample (N=500) of diseases with >= 8 annotated HPO terms of which
    >= 4 have at least one synonym.
  * Query: 4 phenotypes drawn (seeded) from the target's annotated terms. Two variants:
      - "names"     : the HPO preferred names
      - "synonyms"  : a synonym of each term (different surface form than the disease text uses)
  * Ground truth: the target disease ID (strict ID match; diseases with identical annotations are not merged).
  * Systems compared on IDENTICAL queries: TF-IDF lexical baseline over the disease text, MiniLM,
    S-PubMedBERT (each with mean_vector and per_phenotype_rrf), plus an HPO-ID-overlap reference that is
    given the oracle HPO IDs.
LIMITATIONS (also written to the report): query terms are drawn from the target's own annotations, so this
measures recovery of a disease from a partial phenotype set, NOT diagnostic accuracy on real patients;
no real patient cohort with confirmed diagnoses is available in this repository. The BioCreative data has
no disease labels, so it cannot serve as retrieval ground truth.
"""
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.append(os.path.abspath("."))
from src.retrieval.disease_retriever import DiseaseRetriever  # noqa: E402
from src.retrieval.store import get_store  # noqa: E402

N_QUERIES, N_PHENOTYPES, SEED, MAX_RANK = 500, 4, 42, 100


def build_queries(config_path, seed=SEED, n_queries=N_QUERIES, exclude_ids=()):
    emb = Path(yaml.safe_load(open(config_path, encoding="utf-8"))["retrieval"]["embeddings_dir"]) / "records"
    diseases = json.load(open(emb / "disease_records.json", encoding="utf-8"))
    hpo = {r["hpo_id"]: r for r in json.load(open(emb / "hpo_records.json", encoding="utf-8"))}
    rng = random.Random(seed)
    eligible = []
    for d in diseases:
        terms = [h for h in d["hpo_ids"] if h in hpo]
        with_syn = [h for h in terms if hpo[h]["synonyms"]]
        if len(terms) >= 8 and len(with_syn) >= N_PHENOTYPES and d["disease_id"] not in exclude_ids:
            eligible.append((d, with_syn))
    sample = rng.sample(eligible, min(n_queries, len(eligible)))
    queries = []
    for d, with_syn in sample:
        ids = rng.sample(with_syn, N_PHENOTYPES)
        queries.append({
            "disease_id": d["disease_id"], "hpo_ids": ids,
            "names": [hpo[h]["name"] for h in ids],
            "synonyms": [rng.choice(hpo[h]["synonyms"]) for h in ids],
        })
    return queries, diseases, len(eligible)


def metrics(ranks, latencies):
    r = np.array(ranks, dtype=float)
    found = r > 0
    return {
        "Recall@1": round(float(np.mean(r == 1)), 4),
        "Recall@5": round(float(np.mean(found & (r <= 5))), 4),
        "Recall@10": round(float(np.mean(found & (r <= 10))), 4),
        "MRR": round(float(np.mean(np.where(found, 1.0 / np.where(found, r, 1), 0.0))), 4),
        "latency_ms_mean": round(float(np.mean(latencies)), 2),
        "latency_ms_p50": round(float(np.percentile(latencies, 50)), 2),
        "latency_ms_p95": round(float(np.percentile(latencies, 95)), 2),
    }


def rank_of(target, ids):
    return ids.index(target) + 1 if target in ids else 0


def calibrate_hpo_tau(config_path="configs/config.yaml", taus=(0.02, 0.05, 0.1, 0.2, 0.5, 1.0), write=True):
    """Pick tau per strategy on 200 queries (seed 7) whose target diseases are DISJOINT from the evaluation set."""
    eval_q, _, _ = build_queries(config_path)
    excl = {q["disease_id"] for q in eval_q}
    cal_q, _, _ = build_queries(config_path, seed=7, n_queries=200, exclude_ids=excl)
    retr = DiseaseRetriever("primary", config_path, store=get_store("primary", config_path))
    out = {"calibration_queries": len(cal_q), "disjoint_from_eval": True, "strategies": {}}
    for strat, attr in (("hpo_expansion", "hpo_tau"), ("hpo_expansion_sym", "hpo_sym_tau")):
        rows = []
        for tau in taus:
            setattr(retr, attr, tau)
            mrrs = []
            for variant in ("names", "synonyms"):
                ranks = [rank_of(q["disease_id"], [c["disease_id"] for c in retr.retrieve_diseases(q[variant], top_k=MAX_RANK, strategy=strat)]) for q in cal_q]
                mrrs.append(metrics(ranks, [0] * len(ranks))["MRR"])
            rows.append({"tau": tau, "MRR_names": mrrs[0], "MRR_synonyms": mrrs[1], "MRR_mean": round(float(np.mean(mrrs)), 4)})
        best = max(rows, key=lambda r: r["MRR_mean"])
        out["strategies"][strat] = {"sweep": rows, "selected_tau": best["tau"], "calibration_MRR_mean": best["MRR_mean"]}
    if write:
        json.dump(out, open("reports/retrieval_tau_calibration.json", "w", encoding="utf-8"), indent=2)
    return out


def evaluate_retrieval(config_path="configs/config.yaml", write=True):
    config = yaml.safe_load(open(config_path, encoding="utf-8"))
    queries, diseases, n_eligible = build_queries(config_path)
    texts = [d["canonical_text"] for d in diseases]
    d_ids = [d["disease_id"] for d in diseases]

    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    mat = tfidf.fit_transform(texts)
    idf = {}
    for d in diseases:
        for h in set(d["hpo_ids"]):
            idf[h] = idf.get(h, 0) + 1
    hpo_sets = [set(d["hpo_ids"]) for d in diseases]

    systems = {}
    retrievers = {}
    for key in ("baseline", "primary"):
        store = get_store(key, config_path)
        retr = DiseaseRetriever(key, config_path, store=store)
        retr.store.encoder.encode(["warm up"])
        retrievers[key] = retr

    results = {}
    for variant in ("names", "synonyms"):
        res = {}
        # lexical TF-IDF
        ranks, lat = [], []
        for q in queries:
            t0 = time.perf_counter()
            v = tfidf.transform([" ".join(q[variant])])
            sims = (mat @ v.T).toarray().ravel()
            order = np.argsort(-sims)[:MAX_RANK]
            lat.append((time.perf_counter() - t0) * 1000)
            ranks.append(rank_of(q["disease_id"], [d_ids[i] for i in order]))
        res["lexical_tfidf"] = metrics(ranks, lat)
        # HPO-ID overlap reference (oracle IDs, identical for both variants)
        ranks, lat = [], []
        n_dis = len(diseases)
        for q in queries:
            t0 = time.perf_counter()
            sc = np.array([sum(np.log(n_dis / idf[h]) for h in q["hpo_ids"] if h in s) for s in hpo_sets])
            order = np.argsort(-sc)[:MAX_RANK]
            lat.append((time.perf_counter() - t0) * 1000)
            ranks.append(rank_of(q["disease_id"], [d_ids[i] for i in order]))
        res["hpo_id_overlap_oracle_reference"] = metrics(ranks, lat)
        for key, label in (("baseline", "minilm"), ("primary", "spubmedbert")):
            for strat in ("mean_vector", "per_phenotype_rrf", "hpo_expansion", "hpo_expansion_sym"):
                ranks, lat = [], []
                for q in queries:
                    t0 = time.perf_counter()
                    cands = retrievers[key].retrieve_diseases(q[variant], top_k=MAX_RANK, strategy=strat)
                    lat.append((time.perf_counter() - t0) * 1000)
                    ranks.append(rank_of(q["disease_id"], [c["disease_id"] for c in cands]))
                res[f"{label}__{strat}"] = metrics(ranks, lat)
        results[variant] = res

    report = {
        "protocol": __doc__.strip(),
        "n_queries": len(queries), "n_eligible_diseases": n_eligible, "phenotypes_per_query": N_PHENOTYPES,
        "seed": SEED, "max_rank_considered": MAX_RANK, "kb_size": len(diseases),
        "models": {k: retrievers[k].info for k in retrievers},
        "results": results,
        "embedding_manifests": {k: {"created_at": retrievers[k].store.manifest["created_at"],
                                     "device": retrievers[k].store.manifest["device"]} for k in retrievers},
    }
    if write:
        Path("reports").mkdir(exist_ok=True)
        json.dump(report, open("reports/retrieval_evaluation.json", "w", encoding="utf-8"), indent=2)
        rows = []
        for variant, res in results.items():
            for system, m in res.items():
                rows.append({"query_variant": variant, "system": system, **m})
        pd.DataFrame(rows).to_csv("reports/retrieval_model_comparison.csv", index=False)
    return report


if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        print(json.dumps(calibrate_hpo_tau(), indent=1))
        sys.exit(0)
    rep = evaluate_retrieval()
    for variant, res in rep["results"].items():
        print(f"\n== {variant} ==")
        print(pd.DataFrame(res).T.to_string())
