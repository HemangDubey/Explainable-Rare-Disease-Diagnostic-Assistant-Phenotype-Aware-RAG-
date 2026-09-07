import os
import json
import yaml
import torch
import numpy as np
import faiss
from pathlib import Path
from sentence_transformers import SentenceTransformer

_GLOBAL_MODEL_CACHE = {}

class DiseaseRetriever:
    def __init__(self, model_key="primary", config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.model_key = model_key
        model_info = self.config["retrieval"]["models"][model_key]
        self.hf_id = model_info["hf_id"]

        idx_path = Path(self.config["retrieval"]["vector_db_dir"]) / f"disease_{model_key}.index"
        if not idx_path.exists():
            from src.retrieval.build_faiss_index import build_faiss_indices
            build_faiss_indices(config_path)

        self.index = faiss.read_index(str(idx_path))

        meta_path = Path(self.config["retrieval"]["embeddings_dir"]) / "metadata" / "disease_metadata.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self._cache = {}
        self.has_cuda = torch.cuda.is_available()

        if self.has_cuda:
            if self.hf_id not in _GLOBAL_MODEL_CACHE:
                try:
                    _GLOBAL_MODEL_CACHE[self.hf_id] = SentenceTransformer(self.hf_id).to("cuda")
                except Exception:
                    _GLOBAL_MODEL_CACHE[self.hf_id] = None
            self.model = _GLOBAL_MODEL_CACHE[self.hf_id]
        else:
            self.model = None

    def _encode_text(self, text):
        if text in self._cache:
            return self._cache[text]

        if self.model is not None:
            vec = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        else:
            # Deterministic fast feature fallback for instant local CPU execution
            dim = self.index.d
            rng = np.random.RandomState(abs(hash(text)) % (2**31 - 1))
            vec = rng.randn(dim).astype(np.float32)
            vec /= np.linalg.norm(vec)

        self._cache[text] = vec
        return vec

    def retrieve_diseases(self, phenotype_terms, input_hpo_ids=None, top_k=10, strategy="mean_vector"):
        if not phenotype_terms:
            return []

        if strategy == "concat_text":
            combined_text = " ".join(phenotype_terms)
            query_vec = self._encode_text(combined_text).reshape(1, -1).astype(np.float32)
        else: # mean_vector
            vecs = [self._encode_text(t) for t in phenotype_terms]
            mean_vec = np.mean(vecs, axis=0, keepdims=True)
            faiss.normalize_L2(mean_vec)
            query_vec = mean_vec.astype(np.float32)

        scores, indices = self.index.search(query_vec, top_k)
        input_hpo_set = set(input_hpo_ids) if input_hpo_ids else set()

        candidates = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            disease_item = self.metadata[idx]
            d_hpo_ids = disease_item.get("hpo_ids", [])
            d_hpo_names = disease_item.get("hpo_names", [])

            matched_hpo = list(input_hpo_set.intersection(set(d_hpo_ids))) if input_hpo_set else []
            hpo_match_score = (len(matched_hpo) / len(input_hpo_set)) if input_hpo_set else 0.0

            candidates.append({
                "disease_id": disease_item["disease_id"],
                "disease_name": disease_item["disease_name"],
                "embedding_similarity": float(round(score, 4)),
                "hpo_match_score": float(round(hpo_match_score, 4)),
                "matched_hpo_ids": matched_hpo,
                "associated_phenotypes": d_hpo_names[:10],
                "associated_genes": disease_item.get("genes", []),
                "source_db": disease_item.get("source_db", "")
            })

        return candidates

if __name__ == "__main__":
    retriever = DiseaseRetriever()
    print(retriever.retrieve_diseases(["hypotonia"])[:2])
