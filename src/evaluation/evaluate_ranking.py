"""Population-aware ranking: weight tuning (VALIDATION only) and A/B/C(/D) ablation (held-out TEST).

Data protocol (simulated patients from HPO annotations, as in Phase 2R; see evaluate_retrieval.py):
  * TEST        500 queries, seed 42 (never used for tuning)
  * VALIDATION  300 queries, seed 11 (disjoint from TEST) -> weights
  * The SAME Phase 2R top-50 candidate pool, queries and ground truth for every configuration; only the
    population evidence component differs.

Configurations
  A  Phase 2R retrieval + phenotype ranking                                   (w_population = 0)
  B  A + gnomAD South Asian population evidence
  C  A + gnomAD South Asian + South-Asian-vs-global comparison
  D  A + IndiGen                                                              (BLOCKED while IndiGen is unavailable)
  E  A + gnomAD global baseline only                                          (extra reference)
Phenotype/retrieval weights are frozen from A's validation search; only w_population is tuned for B/C/E, and only if
at least `min_candidate_coverage_for_tuning` of validation candidate slots carry a population signal; otherwise
w_population = 0 and the report says so.

CAVEAT: simulated queries are sampled uniformly over diseases, so they carry no information about how common a
disease is in a population; a frequency prior cannot be expected to help here, and a null result does not show it
would not help on real patient populations. The overlap feature uses the query's true HPO IDs (optimistic).
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.append(os.path.abspath("."))
from src.evaluation.evaluate_retrieval import build_queries, rank_of  # noqa: E402
from src.population.population_lookup import PopulationLookup  # noqa: E402
from src.ranking.disease_ranker import EXPERIMENTS, DiseaseRanker  # noqa: E402
from src.ranking.population_prior import PopulationPriorEngine  # noqa: E402
from src.retrieval.disease_retriever import DiseaseRetriever  # noqa: E402
from src.retrieval.store import get_store  # noqa: E402

POOL = 50
W_HPO_GRID = [round(x, 1) for x in np.arange(0.0, 1.01, 0.1)]
W_POP_GRID = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
SENSITIVITY_WEIGHTS = [0.05, 0.1, 0.2]     # fixed in advance; exploratory only, never used for selection
CONFIGS = {
    "A_retrieval_phenotype": "rag_only",
    "B_plus_south_asian": "rag_south_asian",
    "C_plus_south_asian_and_global_comparison": "rag_south_asian_global",
    "D_plus_indigen": "rag_indigen",
    "E_plus_global_baseline_only": "rag_gnomad_global",
}


def metrics(ranks):
    r = np.array(ranks, dtype=float); f = r > 0
    rr = np.where(f, 1.0 / np.where(f, r, 1), 0.0)
    ndcg = np.where(f & (r <= 10), 1.0 / np.log2(np.where(f, r, 1) + 1), 0.0)
    return {"Recall@1": round(float(np.mean(r == 1)), 4), "Recall@5": round(float(np.mean(f & (r <= 5))), 4),
            "Recall@10": round(float(np.mean(f & (r <= 10))), 4), "MRR": round(float(np.mean(rr)), 4),
            "NDCG@10": round(float(np.mean(ndcg)), 4)}


def rr_vec(ranks):
    r = np.array(ranks, dtype=float)
    return np.where(r > 0, 1.0 / np.where(r > 0, r, 1), 0.0)


def paired_bootstrap(a_ranks, b_ranks, n=2000, seed=0):
    """95% CI of mean(RR_b - RR_a) over queries (paired resampling)."""
    d = rr_vec(b_ranks) - rr_vec(a_ranks)
    rng = np.random.default_rng(seed)
    means = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    verdict = "NO SIGNIFICANT CHANGE"
    if lo > 0:
        verdict = "IMPROVES"
    elif hi < 0:
        verdict = "DEGRADES"
    return {"mean_rr_difference": round(float(d.mean()), 5), "ci95": [round(float(lo), 5), round(float(hi), 5)], "verdict": verdict,
            "queries_changed": int((d != 0).sum())}


def build_pools(retr, queries, variant):
    return [retr.retrieve_diseases(q[variant], input_hpo_ids=q["hpo_ids"], top_k=POOL) for q in queries]


def run_config(ranker, queries, pools, weights, exp):
    ranks, lat, ranked_all = [], [], []
    for q, pool in zip(queries, pools):
        t0 = time.perf_counter()
        ranked = ranker.rank_candidates(pool, weights=weights, exp_config=exp)
        lat.append((time.perf_counter() - t0) * 1000)
        ranks.append(rank_of(q["disease_id"], [c["disease_id"] for c in ranked]))
        ranked_all.append(ranked)
    return ranks, lat, ranked_all


def slot_coverage(ranker, pools, exp, queries=None):
    slots = with_sig = 0
    flags = EXPERIMENTS[exp]
    tgt = tgt_sig = 0
    for i, pool in enumerate(pools):
        for c in pool:
            slots += 1
            has = ranker.population_for(c.get("associated_genes", []) or [], flags)["population_signal"] is not None
            with_sig += has
            if queries is not None and c["disease_id"] == queries[i]["disease_id"]:
                tgt += 1; tgt_sig += has
    out = {"candidate_slots": slots, "with_population_signal": with_sig, "coverage": round(with_sig / max(slots, 1), 4)}
    if queries is not None:
        out["targets_in_pool"] = tgt; out["targets_with_signal"] = tgt_sig
    return out


def blocked_reason(lookup, exp, cov):
    flags = EXPERIMENTS[exp]
    if flags["use_indigen"] and not lookup.indigen.available:
        return "BLOCKED - IndiGen unavailable (access required); no South Asian or other data substituted"
    if flags["use_gnomad_sas"] or flags["use_gnomad_global"] or flags["use_sas_vs_global"]:
        if lookup.cdf_global.n < lookup.min_n:
            return f"INSUFFICIENT EVIDENCE - population signal undefined ({lookup.cdf_global.n} reference genes < {lookup.min_n})"
    if cov is not None and cov["with_population_signal"] == 0:
        return "INSUFFICIENT EVIDENCE - no candidate carries a population signal"
    return None


def evaluate(config_path="configs/config.yaml", write=True):
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    min_cov = float(cfg["population"].get("min_candidate_coverage_for_tuning", 0.25))
    test_q, _, _ = build_queries(config_path)
    val_q, _, _ = build_queries(config_path, seed=11, n_queries=300, exclude_ids={q["disease_id"] for q in test_q})
    retr = DiseaseRetriever("primary", config_path, store=get_store("primary", config_path))
    lookup = PopulationLookup(config_path)
    ranker = DiseaseRanker(config_path, population_engine=PopulationPriorEngine(config_path, lookup=lookup))
    retr.store.encoder.encode(["warm up"])
    t0 = time.perf_counter()
    val_pool = build_pools(retr, val_q, "names")
    test_pool = {v: build_pools(retr, test_q, v) for v in ("names", "synonyms")}
    pool_time = time.perf_counter() - t0

    # ---- A: tune phenotype/retrieval weights on VALIDATION, then freeze ----
    rows = []
    for w_h in W_HPO_GRID:
        ranks, _, _ = run_config(ranker, val_q, val_pool, {"w_phenotype": w_h, "w_retrieval": round(1 - w_h, 4), "w_population": 0.0}, "rag_only")
        rows.append({"config": "A_retrieval_phenotype", "w_phenotype": w_h, "w_retrieval": round(1 - w_h, 4), "w_population": 0.0, **metrics(ranks)})
    best_a = max(rows, key=lambda r: (r["MRR"], r["Recall@1"]))
    frozen = {"w_phenotype": best_a["w_phenotype"], "w_retrieval": best_a["w_retrieval"]}

    # ---- population weight per config (validation), only if coverage is sufficient ----
    chosen, tuning_notes = {}, {}
    for name, exp in CONFIGS.items():
        if name.startswith("A_"):
            continue
        cov = slot_coverage(ranker, val_pool, exp)
        why = blocked_reason(lookup, exp, cov)
        if why:
            chosen[name] = None; tuning_notes[name] = why; continue
        if cov["coverage"] < min_cov:
            chosen[name] = 0.0
            tuning_notes[name] = (f"Population weight could not be reliably estimated from the available evidence coverage "
                                  f"({cov['coverage']:.1%} of validation candidate slots < {min_cov:.0%}); w_population = 0.")
            continue
        best = (-1, None)
        for w_p in [0.0] + W_POP_GRID:
            ranks, _, _ = run_config(ranker, val_q, val_pool, {**frozen, "w_population": w_p}, exp)
            m = metrics(ranks)
            rows.append({"config": name, **frozen, "w_population": w_p, **m, "validation_slot_coverage": cov["coverage"]})
            if (m["MRR"], -w_p) > (best[0], -(best[1] or 0)):     # ties -> smaller weight
                best = (m["MRR"], w_p)
        chosen[name] = best[1]
        tuning_notes[name] = f"selected on validation MRR; slot coverage {cov['coverage']:.1%}"

    # ---- frozen-weight TEST ablation (identical queries/candidates/ground truth) ----
    results, rank_changes, tests = {}, {}, {}
    for variant in ("names", "synonyms"):
        pools = test_pool[variant]
        res, base_ranks, base_ranked = {}, None, None
        w0 = {**frozen, "w_population": 0.0}
        base_ranks, base_lat, base_ranked = run_config(ranker, test_q, pools, w0, "rag_only")
        res["Phase2R_retrieval_order_reference"] = metrics([rank_of(q["disease_id"], [c["disease_id"] for c in p]) for q, p in zip(test_q, pools)])
        res["A_retrieval_phenotype"] = {**metrics(base_ranks), "latency_ms_mean": round(float(np.mean(base_lat)), 3), "weights": w0,
                                         "population_coverage": None}
        for name, exp in CONFIGS.items():
            if name.startswith("A_"):
                continue
            cov = slot_coverage(ranker, pools, exp, test_q)
            why = blocked_reason(lookup, exp, cov)
            if why or chosen[name] is None:
                res[name] = {"status": why or "BLOCKED"}; continue
            w = {**frozen, "w_population": chosen[name]}
            ranks, lat, ranked = run_config(ranker, test_q, pools, w, exp)
            res[name] = {**metrics(ranks), "latency_ms_mean": round(float(np.mean(lat)), 3), "weights": w, "population_coverage": cov,
                         "weight_note": tuning_notes[name]}
            tests[f"{variant}:{name}"] = paired_bootstrap(base_ranks, ranks)
            # PRE-SPECIFIED, UNTUNED sensitivity analysis at fixed population weights (descriptive only; nothing is selected from it)
            sens = {}
            for w_s in SENSITIVITY_WEIGHTS:
                r_s, _, ranked_s = run_config(ranker, test_q, pools, {**frozen, "w_population": w_s}, exp)
                moved = [abs(c["rank_change"]) for rr in ranked_s for c in rr if c["rank_change"] != 0]
                sens[str(w_s)] = {**metrics(r_s), "vs_A": paired_bootstrap(base_ranks, r_s),
                                  "top1_changed": sum(a[0]["disease_id"] != b[0]["disease_id"] for a, b in zip(base_ranked, ranked_s)),
                                  "top5_membership_changed": sum({x["disease_id"] for x in a[:5]} != {x["disease_id"] for x in b[:5]} for a, b in zip(base_ranked, ranked_s)),
                                  "candidates_promoted": sum(c["rank_change"] > 0 for rr in ranked_s for c in rr),
                                  "candidates_demoted": sum(c["rank_change"] < 0 for rr in ranked_s for c in rr),
                                  "mean_abs_displacement_when_moved": round(float(np.mean(moved)), 3) if moved else 0.0}
            res[name]["sensitivity_untuned"] = sens
            a_ranked = base_ranked
            top1 = sum(a[0]["disease_id"] != b[0]["disease_id"] for a, b in zip(a_ranked, ranked))
            top5 = sum({x["disease_id"] for x in a[:5]} != {x["disease_id"] for x in b[:5]} for a, b in zip(a_ranked, ranked))
            disp = [abs(c["rank_change"]) for r in ranked for c in r if c["rank_change"] != 0]
            rank_changes[f"{variant}:{name}"] = {
                "queries": len(test_q), "top1_changed": top1, "top5_membership_changed": top5,
                "candidates_promoted": sum(c["rank_change"] > 0 for r in ranked for c in r),
                "candidates_demoted": sum(c["rank_change"] < 0 for r in ranked for c in r),
                "mean_abs_displacement_when_moved": round(float(np.mean(disp)), 3) if disp else 0.0}
        results[variant] = res

    kb = json.load(open("data/embeddings/records/disease_records.json", encoding="utf-8"))
    all_genes = sorted({g for d in kb for g in d["genes"]})
    infos = {g: lookup.lookup_gene(g) for g in all_genes}
    g_av = sum(i["gnomad"]["status"] == "available" for i in infos.values())
    sas_av = sum(i["gnomad"]["status"] == "available" and i["gnomad"].get("caf_sas") is not None for i in infos.values())
    n_var = sum(len(g["rec"].get("plp_variants", [])) for g in lookup.genes.values())
    n_sas = sum(1 for g in lookup.genes.values() for v in g["rec"].get("plp_variants", []) if (v.get("exome") or {}).get("sas_an"))
    pop_cov = {
        "total_diseases": len(kb), "diseases_with_genes": sum(bool(d["genes"]) for d in kb),
        "total_disease_associated_genes": len(all_genes),
        "genes_in_clinvar": sum(i["mapping_status"] in ("mapped", "alias_resolved") for i in infos.values()),
        "genes_with_gnomad_global_evidence": g_av, "gnomad_global_coverage_pct": round(100 * g_av / len(all_genes), 2),
        "genes_with_gnomad_south_asian_evidence": sas_av, "gnomad_south_asian_coverage_pct": round(100 * sas_av / len(all_genes), 2),
        "genes_not_found_or_without_plp": sum(i["gnomad"]["status"] == "not_found" for i in infos.values()),
        "genes_unavailable_not_ingested": sum(i["gnomad"]["status"] == "unavailable" for i in infos.values()),
        "clinvar_plp_variants_matched_in_gnomad_global": n_var,
        "clinvar_plp_variants_with_south_asian_counts": n_sas,
        "global_and_south_asian_matched_variants": n_sas,
        "indigen_status": "UNAVAILABLE - access required" if not lookup.indigen.available else "available",
        "genes_with_indigen_data": sum(i["indigen"]["status"] == "available" for i in infos.values()),
        "reference_genes_for_signal": lookup.cdf_global.n, "reference_genes_for_enrichment": lookup.cdf_enrich.n,
        "reference_min_required": lookup.min_n, "signal_defined": lookup.cdf_global.n >= lookup.min_n,
        "candidate_slot_coverage_test": {c: slot_coverage(ranker, test_pool["names"], e, test_q) for c, e in CONFIGS.items() if not c.startswith("A_")},
        "candidate_slot_coverage_validation": {c: slot_coverage(ranker, val_pool, e) for c, e in CONFIGS.items() if not c.startswith("A_")},
    }
    report = {"protocol": __doc__.strip(), "n_test_queries": len(test_q), "n_validation_queries": len(val_q), "candidate_pool": POOL,
              "frozen_phenotype_retrieval_weights": frozen, "validation_best_A": best_a, "chosen_population_weights": chosen,
              "weight_notes": tuning_notes, "test_results": results, "paired_bootstrap_vs_A": tests, "rank_changes": rank_changes,
              "population_coverage": pop_cov, "timing_s": {"pool_retrieval_total": round(pool_time, 1)}}
    if write:
        Path("reports").mkdir(exist_ok=True)
        pd.DataFrame(rows).to_csv("reports/ranking_weight_search.csv", index=False)
        json.dump({"frozen_phenotype_retrieval": frozen, "population_weights": chosen, "notes": tuning_notes, "validation_best_A": best_a},
                  open("reports/best_ranking_weights.json", "w", encoding="utf-8"), indent=2, default=float)
        json.dump(report, open("reports/ranking_evaluation.json", "w", encoding="utf-8"), indent=2, default=float)
        json.dump(pop_cov, open("reports/population_coverage.json", "w", encoding="utf-8"), indent=2, default=float)
        flat = []
        for v, res in results.items():
            for k, m in res.items():
                flat.append({"query_variant": v, "configuration": k, **{kk: vv for kk, vv in m.items() if kk not in ("weights", "population_coverage", "sensitivity_untuned")},
                             "w_population": (m.get("weights") or {}).get("w_population"),
                             "slot_coverage": (m.get("population_coverage") or {}).get("coverage"),
                             "vs_A": tests.get(f"{v}:{k}", {}).get("verdict")})
                for w_s, sm in (m.get("sensitivity_untuned") or {}).items():
                    flat.append({"query_variant": v, "configuration": f"{k} [untuned sensitivity w_population={w_s}]",
                                 **{kk: sm[kk] for kk in ("Recall@1", "Recall@5", "Recall@10", "MRR", "NDCG@10")},
                                 "w_population": float(w_s), "slot_coverage": (m.get("population_coverage") or {}).get("coverage"),
                                 "vs_A": sm["vs_A"]["verdict"]})
        pd.DataFrame(flat).to_csv("reports/ranking_ablation.csv", index=False)
    return report


if __name__ == "__main__":
    rep = evaluate()
    print(json.dumps({k: rep[k] for k in ("frozen_phenotype_retrieval_weights", "chosen_population_weights", "test_results", "paired_bootstrap_vs_A", "rank_changes")}, indent=1, default=float))
