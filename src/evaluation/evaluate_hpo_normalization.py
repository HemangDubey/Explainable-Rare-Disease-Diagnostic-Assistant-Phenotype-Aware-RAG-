"""HPO normalisation evaluation on REAL clinician annotations (BioCreative VIII Track 3).

Ground truth: each annotated span's text -> the clinician-assigned HPO term. Only positive (non-negated),
continuous-span annotations with a real HPO ID are used. Gold IDs from the 2022 HPO release are resolved to
the current HPO via alt_id / replaced_by; annotations whose gold term is obsolete without a unique
replacement are excluded and counted.

Protocol: the semantic threshold is calibrated on the TRAIN file; results are reported on the TEST half of the
dev file (the same seeded split used for NER). No labels are invented.
"""
import json
import sys
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.append(os.path.abspath("."))
from src.knowledge.hpo_normalizer import HPONormalizer  # noqa: E402

MATCHED = ("exact", "synonym", "lexical", "semantic")


def load_annotations(config, which):
    raw = Path(config["dataset"]["raw_dir"])
    df = pd.read_csv(raw / config["dataset"][("train_file" if which == "train" else "dev_file")], sep="\t", dtype=str)
    if which == "test":      # identical split logic to src/data/convert_to_bio.py
        ids = df["StringID"].unique()
        np.random.seed(config["training"]["seed"])
        shuffled = ids.copy()
        np.random.shuffle(shuffled)
        test_ids = set(shuffled[len(shuffled) // 2:])
        df = df[df["StringID"].isin(test_ids)]
    rows = []
    for _, r in df.iterrows():
        if pd.isna(r["Term"]) or r["Term"] == "NA" or r["Negated"] == "X":
            continue
        span = r["Spans"]
        if pd.isna(span) or span == "NA" or "," in span or "-" not in span:
            continue
        s, e = span.split("-")
        phrase = r["Text"][int(s):int(e)].strip()
        if phrase:
            rows.append({"phrase": phrase, "gold": r["Term"]})
    return rows


def prepare(rows, normalizer):
    kept, excluded = [], 0
    for r in rows:
        gold = normalizer.res.resolve_id(r["gold"])
        if gold is None:
            excluded += 1
        else:
            kept.append({"phrase": r["phrase"], "gold": gold})
    return kept, excluded


def semantic_hits(normalizer, phrases, k=5):
    vecs = normalizer.search.store.encoder.encode(phrases, batch_size=64)
    return normalizer.search.search_vectors(vecs, k)


def calibrate(normalizer, rows, thresholds, margins, min_precision=0.85, min_accepted=20):
    """Semantic-stage precision/coverage for each (threshold, margin) on TRAIN data.

    Selection rule (stated up front, applied to TRAIN only): maximise coverage subject to
    precision >= min_precision and at least min_accepted accepted phrases.
    """
    lex = [normalizer._lexical_stages(r["phrase"]) for r in rows]
    idx = [i for i, x in enumerate(lex) if x is None]
    hits = semantic_hits(normalizer, [rows[i]["phrase"] for i in idx])
    sweep = []
    for th in thresholds:
        for mg in margins:
            acc = corr = 0
            for i, h in zip(idx, hits):
                if h and h[0]["score"] >= th and (len(h) < 2 or h[0]["score"] - h[1]["score"] >= mg):
                    acc += 1
                    corr += h[0]["hpo_id"] == rows[i]["gold"]
            sweep.append({"threshold": th, "margin": mg, "accepted": acc,
                          "coverage_of_semantic_stage": round(acc / max(len(idx), 1), 4),
                          "precision": round(corr / acc, 4) if acc else None})
    ok = [x for x in sweep if x["precision"] is not None and x["precision"] >= min_precision and x["accepted"] >= min_accepted]
    selected = max(ok, key=lambda x: x["coverage_of_semantic_stage"]) if ok else None
    return {"n_phrases": len(rows), "n_reaching_semantic_stage": len(idx),
            "selection_rule": f"max coverage s.t. precision>={min_precision} and accepted>={min_accepted}",
            "selected_operating_point": selected, "sweep": sweep}


def evaluate(normalizer, rows):
    results = normalizer.normalize_many([r["phrase"] for r in rows])
    hits = semantic_hits(normalizer, [r["phrase"] for r in rows])
    n = len(rows)
    by_method = defaultdict(lambda: {"n": 0, "correct": 0})
    status_counts, correct_total, amb_contains = Counter(), 0, 0
    for r, res, h in zip(rows, results, hits):
        status_counts[res["status"]] += 1
        if res["status"] in MATCHED:
            by_method[res["status"]]["n"] += 1
            ok = res["hpo_id"] == r["gold"]
            by_method[res["status"]]["correct"] += ok
            correct_total += ok
        elif res["status"] == "ambiguous":
            amb_contains += any(c["hpo_id"] == r["gold"] for c in res["candidates"])
    matched = sum(status_counts[s] for s in MATCHED)
    top5 = sum(any(x["hpo_id"] == r["gold"] for x in h) for r, h in zip(rows, hits))
    return {
        "n_annotations": n,
        "status_rates": {s: round(status_counts[s] / n, 4) for s in (*MATCHED, "ambiguous", "unmatched")},
        "accuracy_overall": round(correct_total / n, 4),
        "precision_when_matched": round(correct_total / matched, 4) if matched else None,
        "coverage_matched": round(matched / n, 4),
        "ambiguous_contains_gold": amb_contains,
        "accuracy_by_method": {m: {"n": v["n"], "accuracy": round(v["correct"] / v["n"], 4) if v["n"] else None} for m, v in by_method.items()},
        "semantic_top5_recall_all_phrases": round(top5 / n, 4),
    }


def run(config_path="configs/config.yaml", write=True):
    config = yaml.safe_load(open(config_path, encoding="utf-8"))
    norm = HPONormalizer(config_path, use_semantic=True)
    train_rows, tr_excl = prepare(load_annotations(config, "train"), norm)
    test_rows, te_excl = prepare(load_annotations(config, "test"), norm)
    th = [0.88, 0.90, 0.92, 0.94, 0.95]
    mg = [0.0, 0.005, 0.01, 0.02, 0.03]
    report = {
        "ground_truth": "BioCreative VIII Track 3 clinician annotations (span text -> HPO ID); real, not synthetic",
        "protocol": "semantic threshold calibrated on TRAIN; reported on TEST half of dev (same seeded split as NER)",
        "config_thresholds": {"lexical": norm.lexical_threshold, "semantic": norm.semantic_threshold, "margin": norm.semantic_margin},
        "calibration_train": {**calibrate(norm, train_rows, th, mg), "excluded_obsolete_gold": tr_excl},
        "test": {**evaluate(norm, test_rows), "excluded_obsolete_gold": te_excl},
        "notes": ["Annotation HPO release is 2022-06-11 vs current ontology 2026-09-01; resolved via alt_id/replaced_by.",
                  "Unmatched and ambiguous phrases count as errors in accuracy_overall.",
                  "Spans are physical-exam fragments; some annotated spans are not plain phenotype names."],
    }
    if write:
        Path("reports").mkdir(exist_ok=True)
        json.dump(report, open("reports/hpo_normalization_evaluation.json", "w", encoding="utf-8"), indent=2)
    return report


if __name__ == "__main__":
    rep = run()
    print(json.dumps(rep["test"], indent=2))
    print("selected on TRAIN:", rep["calibration_train"]["selected_operating_point"])
