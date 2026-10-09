"""Build FAISS indexes from the REAL embeddings produced by embed_knowledge_base.py.

One pair of exact inner-product indexes (HPO, disease) per model - vectors from different
models are never mixed:
    data/vector_db/spubmedbert/{hpo,disease}.index
    data/vector_db/minilm/{hpo,disease}.index
Index position i corresponds to record i in data/embeddings/records/*.json.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
import yaml

sys.path.append(os.path.abspath("."))


def build_faiss_indices(config_path="configs/config.yaml", model_keys=("primary", "baseline"), rebuild=False):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    emb_root = Path(config["retrieval"]["embeddings_dir"])
    db_root = Path(config["retrieval"]["vector_db_dir"])

    n_records = {
        "hpo": len(json.load(open(emb_root / "records" / "hpo_records.json", encoding="utf-8"))),
        "disease": len(json.load(open(emb_root / "records" / "disease_records.json", encoding="utf-8"))),
    }
    for key in model_keys:
        info = config["retrieval"]["models"][key]
        emb_dir, db_dir = emb_root / info["key_dir"], db_root / info["key_dir"]
        manifest_path = emb_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No embedding manifest for {info['name']} at {manifest_path}. Run embed_knowledge_base.py first.")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        if manifest["model"] != info["hf_id"]:
            raise ValueError(f"Manifest model {manifest['model']} != configured {info['hf_id']}.")
        db_dir.mkdir(parents=True, exist_ok=True)
        if (db_dir / "index_manifest.json").exists() and not rebuild:
            print(f"{info['name']}: indexes exist, skipping (use --rebuild).")
            continue
        index_info = {}
        for kind in ("hpo", "disease"):
            vecs = np.load(emb_dir / f"{kind}_vectors.npy").astype(np.float32)
            if vecs.shape[0] != n_records[kind] or vecs.shape[0] != manifest["counts"][kind]:
                raise ValueError(f"{info['name']} {kind}: {vecs.shape[0]} vectors vs {n_records[kind]} records / manifest {manifest['counts'][kind]}.")
            if vecs.shape[1] != info["dim"] or not np.isfinite(vecs).all():
                raise ValueError(f"{info['name']} {kind}: bad dimension or non-finite values.")
            index = faiss.IndexFlatIP(vecs.shape[1])
            index.add(vecs)
            if index.ntotal != n_records[kind]:
                raise ValueError(f"{info['name']} {kind}: index count {index.ntotal} != records {n_records[kind]}.")
            faiss.write_index(index, str(db_dir / f"{kind}.index"))
            index_info[kind] = {"ntotal": int(index.ntotal), "dim": int(vecs.shape[1]), "type": "IndexFlatIP"}
            print(f"{info['name']} {kind}: {index.ntotal} vectors, dim {vecs.shape[1]} -> {db_dir / (kind + '.index')}")
        with open(db_dir / "index_manifest.json", "w", encoding="utf-8") as f:
            json.dump({"model": info["hf_id"], "built_at": datetime.now(timezone.utc).isoformat(),
                       "embedding_created_at": manifest["created_at"], "indexes": index_info}, f, indent=2)
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    build_faiss_indices(rebuild=a.rebuild)
