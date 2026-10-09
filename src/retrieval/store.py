"""Loads one model's FAISS indexes + aligned source records + manifest (validated, fail-loud)."""
import json
import threading
from pathlib import Path

import faiss
import yaml

from src.retrieval.encoder import TextEncoder, get_encoder


class RetrievalStoreError(RuntimeError):
    pass


_STORES = {}
_LOCK = threading.Lock()


def get_store(model_key="primary", config_path="configs/config.yaml"):
    with _LOCK:
        if (model_key, config_path) not in _STORES:
            _STORES[(model_key, config_path)] = RetrievalStore(model_key, config_path)
        return _STORES[(model_key, config_path)]


class RetrievalStore:
    def __init__(self, model_key="primary", config_path="configs/config.yaml", encoder: TextEncoder = None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        info = self.config["retrieval"]["models"][model_key]
        self.model_key = model_key
        self.config_path = config_path
        self.model_name = info["name"]
        self.hf_id = info["hf_id"]
        emb_root = Path(self.config["retrieval"]["embeddings_dir"])
        db_dir = Path(self.config["retrieval"]["vector_db_dir"]) / info["key_dir"]

        manifest_path = emb_root / info["key_dir"] / "manifest.json"
        if not manifest_path.exists() or not (db_dir / "disease.index").exists() or not (db_dir / "hpo.index").exists():
            raise RetrievalStoreError(
                f"Real embeddings/indexes for {self.model_name} are missing. "
                "Run: python src/retrieval/embed_knowledge_base.py && python src/retrieval/build_faiss_index.py"
            )
        self.manifest = json.load(open(manifest_path, encoding="utf-8"))
        if self.manifest["model"] != self.hf_id:
            raise RetrievalStoreError(f"Embeddings were made with {self.manifest['model']}, config expects {self.hf_id}.")

        self.hpo_records = json.load(open(emb_root / "records" / "hpo_records.json", encoding="utf-8"))
        self.disease_records = json.load(open(emb_root / "records" / "disease_records.json", encoding="utf-8"))
        self.hpo_index = faiss.read_index(str(db_dir / "hpo.index"))
        self.disease_index = faiss.read_index(str(db_dir / "disease.index"))
        if self.hpo_index.ntotal != len(self.hpo_records) or self.disease_index.ntotal != len(self.disease_records):
            raise RetrievalStoreError("FAISS index size does not match the source records (stale index?).")
        if self.hpo_index.d != self.manifest["embedding_dimension"]:
            raise RetrievalStoreError("Index dimension does not match the embedding manifest.")
        self.hpo_by_id = {r["hpo_id"]: r for r in self.hpo_records}
        self._encoder = encoder

    @property
    def encoder(self) -> TextEncoder:
        if self._encoder is None:
            self._encoder = get_encoder(self.model_key, self.config_path)
        return self._encoder
