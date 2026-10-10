"""Runtime artifact bundle for deployment (Phase 9).

`pack`     copies ONLY what the API needs at run time into a directory (no training checkpoints, no raw datasets, no logs):
           models/biomedbert_phenotype_ner (weights + tokenizer), data/embeddings, data/vector_db/<primary>, data/processed,
           data/raw/gnomad/gene_cache, data/demo.
`upload`   pushes a packed directory to a Hugging Face Hub repo (needs HF_TOKEN, set in your shell; never commit it).
`fetch`    downloads the bundle into the application root (used at image build / first boot; resumable and cached by the Hub client).
`verify`   fails clearly if a required artifact is missing (the API also refuses to fabricate results without them).

    python scripts/artifacts_bundle.py pack  --out build/artifacts
    python scripts/artifacts_bundle.py upload --src build/artifacts --repo <user>/<repo> [--private]
    python scripts/artifacts_bundle.py fetch  --repo <user>/<repo> [--root .]
    python scripts/artifacts_bundle.py verify [--root .]
"""
import argparse
import os
import shutil
import sys

NER_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "metadata.json", "val_metrics.json"]
TREES = ["data/embeddings", "data/vector_db/spubmedbert", "data/processed", "data/raw/gnomad/gene_cache", "data/demo"]
REQUIRED = ["models/biomedbert_phenotype_ner/model.safetensors", "models/biomedbert_phenotype_ner/config.json",
            "data/vector_db/spubmedbert/disease.index", "data/vector_db/spubmedbert/hpo.index",
            "data/embeddings/spubmedbert/disease_vectors.npy", "data/embeddings/records/disease_records.json",
            "data/processed/hpo/hpo_terms.json", "data/processed/population/clinvar_plp_grch38.parquet"]
SKIP_DIRS = {"_chunks", "checkpoints", "__pycache__"}
SKIP_SUFFIX = (".tmp", ".incomplete")


def _size(path):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)


def pack(out, root="."):
    if os.path.exists(out):
        sys.exit(f"{out} already exists; remove it first")
    n = 0
    for f in NER_FILES:
        src = os.path.join(root, "models/biomedbert_phenotype_ner", f)
        if os.path.exists(src):
            os.makedirs(os.path.join(out, "models/biomedbert_phenotype_ner"), exist_ok=True)
            shutil.copy2(src, os.path.join(out, "models/biomedbert_phenotype_ner", f)); n += 1
    for tree in TREES:
        for d, dirs, files in os.walk(os.path.join(root, tree)):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            rel = os.path.relpath(d, root)
            for f in files:
                if f.endswith(SKIP_SUFFIX) or f.endswith(".db"):
                    continue
                os.makedirs(os.path.join(out, rel), exist_ok=True)
                shutil.copy2(os.path.join(d, f), os.path.join(out, rel, f)); n += 1
    print(f"packed {n} files, {_size(out) / 1e6:.0f} MB -> {out}")
    verify(out)


def verify(root="."):
    missing = [p for p in REQUIRED if not os.path.exists(os.path.join(root, p))]
    if missing:
        sys.exit("MISSING required artifacts (the API will not run the clinical pipeline without them):\n  " + "\n  ".join(missing))
    print("all required artifacts present")


def upload(src, repo, private=False):
    from huggingface_hub import HfApi
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_repo(repo, repo_type="model", private=private, exist_ok=True)
    api.upload_folder(folder_path=src, repo_id=repo, repo_type="model", commit_message="Runtime artifact bundle")
    print("uploaded to", repo)


def fetch(repo, root="."):
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=repo, repo_type="model", local_dir=root, token=os.environ.get("HF_TOKEN"))
    verify(root)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pack", "upload", "fetch", "verify"])
    ap.add_argument("--out", default="build/artifacts")
    ap.add_argument("--src", default="build/artifacts")
    ap.add_argument("--repo")
    ap.add_argument("--root", default=".")
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()
    if a.cmd == "pack":
        pack(a.out, a.root)
    elif a.cmd == "verify":
        verify(a.root)
    elif not a.repo:
        sys.exit("--repo is required")
    elif a.cmd == "upload":
        upload(a.src, a.repo, a.private)
    else:
        fetch(a.repo, a.root)
