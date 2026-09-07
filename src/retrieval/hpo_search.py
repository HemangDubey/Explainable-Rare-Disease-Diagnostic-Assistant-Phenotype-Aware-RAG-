import os
import json
import yaml
import numpy as np
import faiss
from pathlib import Path
from sentence_transformers import SentenceTransformer

class HPOSearchEngine:
    def __init__(self, model_key="primary", config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.model_key = model_key
        model_info = self.config["retrieval"]["models"][model_key]
        self.hf_id = model_info["hf_id"]

        # Load FAISS index
        idx_path = Path(self.config["retrieval"]["vector_db_dir"]) / f"hpo_{model_key}.index"
        if not idx_path.exists():
            raise FileNotFoundError(f"FAISS HPO index not found at {idx_path}. Run build_faiss_index.py first.")

        self.index = faiss.read_index(str(idx_path))

        # Load metadata mapping
        meta_path = Path(self.config["retrieval"]["embeddings_dir"]) / "metadata" / "hpo_metadata.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self.model = SentenceTransformer(self.hf_id)

    def search(self, query_text, top_k=5):
        query_vec = self.model.encode([query_text], normalize_embeddings=True).astype(np.float32)
        scores, indices = self.index.search(query_vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            meta_item = self.metadata[idx]
            results.append({
                "hpo_id": meta_item["hpo_id"],
                "name": meta_item["name"],
                "score": float(round(score, 4)),
                "canonical_text": meta_item.get("canonical_text", "")
            })

        return results

if __name__ == "__main__":
    searcher = HPOSearchEngine()
    print("HPO Search for 'abnormal gait':")
    print(json.dumps(searcher.search("abnormal gait"), indent=2))
