"""Validate that stored embeddings/indexes are genuine model outputs and internally consistent.

Writes reports/embedding_validation.json and exits non-zero if any check fails.
"""
import json
import os
import re
import sys
from pathlib import Path

import faiss
import numpy as np
import yaml

sys.path.append(os.path.abspath("."))
from src.retrieval.embed_knowledge_base import sha256_file  # noqa: E402
from src.retrieval.encoder import TextEncoder  # noqa: E402

TOL_STORED_VS_FRESH = 1e-4     # fp32 differences from batch composition are ~1e-7; anything larger is a real mismatch
N_SAMPLE = 60
FORBIDDEN = [r"RandomState", r"np\.random", r"numpy\.random", r"\brandn\b", r"\bhash\("]
SCAN_DIRS = ["src/retrieval", "src/pipeline", "src/knowledge", "src/inference"]


def validate(config_path="configs/config.yaml"):
    config = yaml.safe_load(open(config_path, encoding="utf-8"))
    emb_root = Path(config["retrieval"]["embeddings_dir"])
    db_root = Path(config["retrieval"]["vector_db_dir"])
    hpo_rec = json.load(open(emb_root / "records" / "hpo_records.json", encoding="utf-8"))
    dis_rec = json.load(open(emb_root / "records" / "disease_records.json", encoding="utf-8"))
    report = {"models": {}, "source_scan": {}, "passed": True}

    def check(bucket, name, ok, detail=""):
        bucket[name] = {"pass": bool(ok), "detail": detail}
        if not ok:
            report["passed"] = False

    # source scan: no random-embedding patterns in retrieval-related code
    hits = []
    for d in SCAN_DIRS:
        for f in Path(d).glob("*.py"):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                for pat in FORBIDDEN:
                    if re.search(pat, line):
                        hits.append(f"{f}:{n}")
    check(report["source_scan"], "no_random_embedding_patterns", not hits, ", ".join(hits))

    for key in ("primary", "baseline"):
        info = config["retrieval"]["models"][key]
        m = {}
        report["models"][info["name"]] = m
        emb_dir, db_dir = emb_root / info["key_dir"], db_root / info["key_dir"]
        manifest = json.load(open(emb_dir / "manifest.json", encoding="utf-8"))
        check(m, "model_identity", manifest["model"] == info["hf_id"], manifest["model"])
        check(m, "dimension", manifest["embedding_dimension"] == info["dim"], str(manifest["embedding_dimension"]))
        enc = TextEncoder(key, config_path)
        for kind, recs in (("hpo", hpo_rec), ("disease", dis_rec)):
            vecs = np.load(emb_dir / f"{kind}_vectors.npy")
            check(m, f"{kind}_count", vecs.shape == (len(recs), info["dim"]), f"{vecs.shape} vs {len(recs)} records")
            check(m, f"{kind}_finite", np.isfinite(vecs).all(), "no NaN/inf" if np.isfinite(vecs).all() else "NaN/inf found")
            norms = np.linalg.norm(vecs, axis=1)
            check(m, f"{kind}_unit_norm", float(np.abs(norms - 1).max()) < 1e-3, f"max |norm-1|={float(np.abs(norms - 1).max()):.2e}")
            check(m, f"{kind}_sha256_matches_manifest", sha256_file(emb_dir / f"{kind}_vectors.npy") == manifest["vectors_sha256"][f"{kind}_vectors.npy"])
            check(m, f"{kind}_records_sha256_matches_manifest", sha256_file(emb_root / "records" / f"{kind}_records.json") == manifest["records_sha256"][f"{kind}_records.json"])
            # stored vectors == freshly generated model outputs
            rng = np.random.RandomState(0)   # used ONLY to choose which records to spot-check
            pick = rng.choice(len(recs), size=min(N_SAMPLE, len(recs)), replace=False)
            fresh = enc.encode([recs[i]["canonical_text"] for i in pick])
            diff = float(np.abs(fresh - vecs[pick]).max())
            check(m, f"{kind}_stored_equals_fresh_model_output", diff < TOL_STORED_VS_FRESH, f"max abs diff {diff:.2e} over {len(pick)} vectors")
            # index alignment
            idx = faiss.read_index(str(db_dir / f"{kind}.index"))
            check(m, f"{kind}_index_count", idx.ntotal == len(recs), f"{idx.ntotal} vs {len(recs)}")
            rec_diff = max(float(np.abs(idx.reconstruct(int(i)) - vecs[i]).max()) for i in pick[:10])
            check(m, f"{kind}_index_matches_vectors", rec_diff < 1e-6, f"max diff {rec_diff:.2e}")
        # behaviour: deterministic, and different inputs differ
        a, b = enc.encode(["hypotonia"]), enc.encode(["hypotonia"])
        check(m, "deterministic", float(np.abs(a - b).max()) < 1e-6, f"max diff {float(np.abs(a - b).max()):.2e}")
        pair = enc.encode(["hypotonia", "cataract"])
        cos = float(pair[0] @ pair[1])
        check(m, "different_inputs_differ", cos < 0.9999, f"cos(hypotonia, cataract)={cos:.4f}")
        # random-projection signature check (the audited bug)
        old = np.random.RandomState(42).randn(len(hpo_rec), info["dim"]).astype(np.float32)
        old /= np.linalg.norm(old, axis=1, keepdims=True)
        sig = float(np.abs(np.load(emb_dir / "hpo_vectors.npy") - old).max())
        check(m, "not_the_old_random_projection", sig > 1e-3, f"max diff vs RandomState(42) projection {sig:.3f}")
        di = json.load(open(db_dir / "index_manifest.json", encoding="utf-8"))
        check(m, "index_manifest_model", di["model"] == info["hf_id"], di["model"])
    Path("reports").mkdir(exist_ok=True)
    json.dump(report, open("reports/embedding_validation.json", "w", encoding="utf-8"), indent=2)
    return report


if __name__ == "__main__":
    rep = validate()
    for model, checks in rep["models"].items():
        bad = [k for k, v in checks.items() if not v["pass"]]
        print(f"{model}: {len(checks) - len(bad)}/{len(checks)} checks passed" + (f"  FAILED: {bad}" if bad else ""))
    print("source scan:", "clean" if rep["source_scan"]["no_random_embedding_patterns"]["pass"] else rep["source_scan"])
    print("OVERALL:", "PASS" if rep["passed"] else "FAIL")
    sys.exit(0 if rep["passed"] else 1)
