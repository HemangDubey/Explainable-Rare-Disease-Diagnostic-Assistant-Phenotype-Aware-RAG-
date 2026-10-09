"""Generate REAL embeddings for the HPO and disease knowledge bases.

Layout (per model, never mixed):
    data/embeddings/records/hpo_records.json        shared source records + canonical text
    data/embeddings/records/disease_records.json
    data/embeddings/<spubmedbert|minilm>/hpo_vectors.npy
    data/embeddings/<spubmedbert|minilm>/disease_vectors.npy
    data/embeddings/<spubmedbert|minilm>/manifest.json

Canonical text is built ONLY from source data (hp.obo / phenotype.hpoa / phenotype_to_genes):
  HPO:     "<name>. Synonyms: a; b. Definition: ..."        (obsolete terms excluded; the HPO id
           is kept in the record metadata, not in the embedded text, because id digits carry no
           semantics)
  Disease: "<name>. Genes: G1, G2. Phenotypes: p1; p2; ..." (genes come before the long phenotype
           list so they survive the model's max_seq_length truncation)
The source HPOA file has no free-text disease descriptions or synonyms, so none are invented.

Generation is chunked and resumable. No random vectors are ever produced: if the model cannot be
loaded the process raises.
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import transformers
import yaml

sys.path.append(os.path.abspath("."))
from src.retrieval.encoder import TextEncoder  # noqa: E402

CHUNK = 1024


def create_hpo_canonical_text(term):
    text = term["name"].strip()
    syns = [s.strip() for s in term.get("synonyms", []) if s.strip()]
    if syns:
        text += ". Synonyms: " + "; ".join(syns)
    if term.get("definition"):
        text += ". Definition: " + term["definition"].strip()
    return text


def create_disease_canonical_text(d):
    text = d["disease_name"].strip()
    if d.get("genes"):
        text += ". Genes: " + ", ".join(d["genes"])
    if d.get("hpo_names"):
        text += ". Phenotypes: " + "; ".join(d["hpo_names"])
    return text


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _source_versions(config):
    versions = {}
    obo = Path(config["hpo"]["raw_dir"]) / config["hpo"]["obo_file"]
    with open(obo, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("data-version:"):
                versions["hpo_obo"] = line.split(":", 1)[1].strip()
                break
    hpoa = Path(config["disease"]["raw_dir"]) / config["disease"]["hpoa_file"]
    with open(hpoa, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("#version:"):
                versions["hpoa"] = line.split(":", 1)[1].strip()
                break
            if not line.startswith("#"):
                break
    return versions


def build_records(config_path="configs/config.yaml"):
    """Write shared, model-independent source records (with canonical text)."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    hpo_terms = json.load(open(Path(config["hpo"]["processed_dir"]) / config["hpo"]["terms_json"], encoding="utf-8"))
    disease_kb = json.load(open(Path(config["disease"]["processed_dir"]) / config["disease"]["disease_kb_json"], encoding="utf-8"))

    hpo_records = []
    for hid, t in hpo_terms.items():
        if t.get("is_obsolete"):
            continue
        hpo_records.append({
            "index": len(hpo_records), "hpo_id": hid, "name": t["name"],
            "synonyms": t.get("synonyms", []), "canonical_text": create_hpo_canonical_text(t),
        })
    disease_records = []
    for did, d in disease_kb.items():
        disease_records.append({
            "index": len(disease_records), "disease_id": d["disease_id"], "disease_name": d["disease_name"],
            "source_db": d["source_db"], "hpo_ids": d["hpo_ids"], "hpo_names": d["hpo_names"],
            "genes": d["genes"], "canonical_text": create_disease_canonical_text(d),
        })
    rec_dir = Path(config["retrieval"]["embeddings_dir"]) / "records"
    rec_dir.mkdir(parents=True, exist_ok=True)
    with open(rec_dir / "hpo_records.json", "w", encoding="utf-8") as f:
        json.dump(hpo_records, f)
    with open(rec_dir / "disease_records.json", "w", encoding="utf-8") as f:
        json.dump(disease_records, f)
    return hpo_records, disease_records, config


def _encode_resumable(encoder, texts, work_dir, tag, log):
    work_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    t_start = time.time()
    n_chunks = (len(texts) + CHUNK - 1) // CHUNK
    for ci in range(n_chunks):
        path = work_dir / f"{tag}_{ci:05d}.npy"
        if path.exists():
            parts.append(np.load(path))
            continue
        chunk = texts[ci * CHUNK:(ci + 1) * CHUNK]
        vecs = encoder.encode(chunk, batch_size=32)
        np.save(path, vecs)
        parts.append(vecs)
        done = min((ci + 1) * CHUNK, len(texts))
        log(f"[{tag}] {done}/{len(texts)} ({time.time() - t_start:.0f}s)")
    return np.concatenate(parts, axis=0)


def embed_knowledge_base(config_path="configs/config.yaml", model_keys=("primary", "baseline"), rebuild=False):
    log = lambda m: print(m, flush=True)  # noqa: E731
    hpo_records, disease_records, config = build_records(config_path)
    emb_root = Path(config["retrieval"]["embeddings_dir"])
    versions = _source_versions(config)

    for key in model_keys:
        info = config["retrieval"]["models"][key]
        out_dir = emb_root / info["key_dir"]
        if (out_dir / "manifest.json").exists() and not rebuild:
            log(f"{info['name']}: manifest exists, skipping (use --rebuild to regenerate).")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        log(f"=== {info['name']} ({info['hf_id']}) ===")
        encoder = TextEncoder(key, config_path)
        log(f"loaded on {encoder.device}, dim={encoder.dim}")

        hpo_texts = [r["canonical_text"] for r in hpo_records]
        dis_texts = [r["canonical_text"] for r in disease_records]
        tok_h = encoder.count_tokens(hpo_texts)
        tok_d = encoder.count_tokens(dis_texts)
        trunc_h = int(sum(t > encoder.max_seq_length for t in tok_h))
        trunc_d = int(sum(t > encoder.max_seq_length for t in tok_d))
        log(f"texts truncated at {encoder.max_seq_length} tokens: HPO {trunc_h}/{len(hpo_texts)}, disease {trunc_d}/{len(dis_texts)}")

        t0 = time.time()
        hpo_vecs = _encode_resumable(encoder, hpo_texts, out_dir / "_chunks", "hpo", log)
        dis_vecs = _encode_resumable(encoder, dis_texts, out_dir / "_chunks", "disease", log)
        np.save(out_dir / "hpo_vectors.npy", hpo_vecs)
        np.save(out_dir / "disease_vectors.npy", dis_vecs)

        manifest = {
            "model": info["hf_id"], "model_name": info["name"], "embedding_dimension": encoder.dim,
            "dtype": str(hpo_vecs.dtype), "normalization": "L2 (inner product == cosine)",
            "pooling": info.get("pooling", "mean"), "max_seq_length": encoder.max_seq_length,
            "device": encoder.device, "created_at": datetime.now(timezone.utc).isoformat(),
            "generation_seconds": round(time.time() - t0, 1),
            "counts": {"hpo": int(hpo_vecs.shape[0]), "disease": int(dis_vecs.shape[0])},
            "truncated_texts": {"hpo": trunc_h, "disease": trunc_d},
            "source_dataset_versions": versions,
            "software": {"torch": torch.__version__, "transformers": transformers.__version__, "python": platform.python_version()},
            "records_sha256": {
                "hpo_records.json": sha256_file(emb_root / "records" / "hpo_records.json"),
                "disease_records.json": sha256_file(emb_root / "records" / "disease_records.json"),
            },
            "vectors_sha256": {
                "hpo_vectors.npy": sha256_file(out_dir / "hpo_vectors.npy"),
                "disease_vectors.npy": sha256_file(out_dir / "disease_vectors.npy"),
            },
        }
        with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        for p in (out_dir / "_chunks").glob("*.npy"):
            p.unlink()
        try:
            (out_dir / "_chunks").rmdir()
        except OSError:      # e.g. a cloud-sync client briefly holding the folder; harmless
            pass
        log(f"{info['name']}: saved HPO {hpo_vecs.shape}, disease {dis_vecs.shape} in {manifest['generation_seconds']}s")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--models", nargs="+", default=["primary", "baseline"], choices=["primary", "baseline"])
    a = ap.parse_args()
    embed_knowledge_base(model_keys=a.models, rebuild=a.rebuild)
