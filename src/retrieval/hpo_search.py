"""Semantic HPO term search over the REAL S-PubMedBERT (or MiniLM) HPO index."""
import numpy as np

from src.retrieval.store import get_store


class HPOSearchEngine:
    def __init__(self, model_key="primary", config_path="configs/config.yaml", store=None):
        self.store = store or get_store(model_key, config_path)

    def search_vectors(self, query_vecs, top_k=5):
        """Batch search. query_vecs: (n, dim) L2-normalised. Returns list (per query) of result lists."""
        scores, indices = self.store.hpo_index.search(np.ascontiguousarray(query_vecs, dtype=np.float32), top_k)
        out = []
        for row_s, row_i in zip(scores, indices):
            res = []
            for s, i in zip(row_s, row_i):
                if i < 0:
                    continue
                rec = self.store.hpo_records[i]
                res.append({"hpo_id": rec["hpo_id"], "name": rec["name"], "score": float(s)})
            out.append(res)
        return out

    def search(self, query_text, top_k=5):
        vec = self.store.encoder.encode([query_text])
        return self.search_vectors(vec, top_k)[0]
