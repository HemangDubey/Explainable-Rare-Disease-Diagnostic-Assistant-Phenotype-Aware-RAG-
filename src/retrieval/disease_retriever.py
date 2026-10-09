"""Disease retrieval over the REAL embedding index (no random / hash-seeded vectors anywhere).

Query vectors always come from the embedding model (src/retrieval/encoder.py). If the model or the
index is unavailable an exception is raised; there is no fallback.

Multi-phenotype strategies
  mean_vector         one query = L2-normalised mean of the phenotype embeddings, single FAISS search.
  per_phenotype_rrf   one FAISS search per phenotype, rankings merged by reciprocal-rank fusion
                      (score = sum 1/(k + rank), k=60, Cormack et al. 2009). Ranks are by cosine
                      against the full index, so a disease supported by several phenotypes rises.
  concat_text         a single query made of the joined phenotype text (kept for comparison).
  hpo_expansion       phenotype-level semantic matching: each phenotype is embedded and compared with EVERY HPO
                      term (real HPO embeddings read from the FAISS HPO index); a disease's score for that
                      phenotype is its best-matching annotated term, sharpened as exp((cos-1)/tau); the final
                      score is the mean over phenotypes (best-match-average, as in Phenomizer-style methods).
                      tau is calibrated on a query set disjoint from the evaluation set (see evaluate_retrieval.py).
  hpo_expansion_sym   symmetric best-match-average (Phenomizer-style): the query->disease score above is averaged
                      with a disease->query score (each annotated disease term matched to its closest query
                      phenotype, averaged over the disease's terms). This breaks the ties that the one-directional
                      score produces between diseases that all annotate every query term, preferring specific diseases.
`embedding_similarity` is always the mean cosine between the disease vector and the phenotype vectors.
"""
import numpy as np
import faiss

from src.retrieval.store import get_store

STRATEGIES = ("mean_vector", "per_phenotype_rrf", "concat_text", "hpo_expansion", "hpo_expansion_sym")


class DiseaseRetriever:
    def __init__(self, model_key="primary", config_path="configs/config.yaml", store=None):
        self.store = store or get_store(model_key, config_path)
        self.model_key = model_key
        self.config = self.store.config
        self.rrf_k = int(self.config["retrieval"].get("rrf_k", 60))
        self.default_strategy = self.config["retrieval"].get("default_multi_phenotype_strategy", "mean_vector")
        self.hpo_tau = float(self.config["retrieval"].get("hpo_expansion_tau", 0.1))
        self.hpo_sym_tau = float(self.config["retrieval"].get("hpo_expansion_sym_tau", 0.1))
        self._hpo_matrix = None
        self.info = {
            "model": self.store.hf_id, "model_name": self.store.model_name, "index": "IndexFlatIP",
            "embedding_dimension": self.store.manifest["embedding_dimension"],
            "index_vectors": self.store.disease_index.ntotal,
        }

    def _hpo_structures(self):
        """HPO vectors (from the FAISS HPO index) and a CSR-style disease -> annotated-HPO-term layout."""
        if self._hpo_matrix is None:
            st = self.store
            self._hpo_matrix = st.hpo_index.reconstruct_n(0, st.hpo_index.ntotal)
            pos = {r["hpo_id"]: i for i, r in enumerate(st.hpo_records)}
            flat, offsets, has = [], [], []
            for rec in st.disease_records:
                idxs = [pos[h] for h in rec["hpo_ids"] if h in pos]
                offsets.append(len(flat))
                has.append(bool(idxs))
                flat.extend(idxs)
            self._flat = np.array(flat, dtype=np.int64)
            self._offsets = np.array(offsets, dtype=np.int64)
            self._has_terms = np.array(has)
        return self._hpo_matrix

    def _hpo_expansion_scores(self, qvecs, symmetric=False):
        H = self._hpo_structures()
        tau = self.hpo_sym_tau if symmetric else self.hpo_tau
        sims = qvecs @ H.T                                       # (n_query, n_hpo) exact cosines
        total = np.zeros(len(self._offsets), dtype=np.float64)
        for row in sims:
            best = np.maximum.reduceat(row[self._flat], self._offsets)
            best = np.where(self._has_terms, best, -1.0)
            total += np.exp((best - 1.0) / tau)
        q2d = total / len(sims)
        if not symmetric:
            return q2d
        # disease -> query: closest query phenotype for every annotated disease term, averaged per disease
        col_best = np.exp((sims.max(axis=0) - 1.0) / tau)        # (n_hpo,)
        counts = np.diff(np.append(self._offsets, len(self._flat)))
        sums = np.add.reduceat(col_best[self._flat], self._offsets)
        d2q = np.where(self._has_terms, sums / np.maximum(counts, 1), 0.0)
        return 0.5 * (q2d + d2q)

    def _encode(self, texts):
        return self.store.encoder.encode(list(texts))

    def search_vector(self, query_vec, top_k):
        scores, idx = self.store.disease_index.search(np.ascontiguousarray(query_vec.reshape(1, -1), dtype=np.float32), top_k)
        return scores[0], idx[0]

    def retrieve_diseases(self, phenotype_terms, input_hpo_ids=None, top_k=10, strategy=None):
        """phenotype_terms: list of phenotype strings (normally normalised HPO names)."""
        phenotype_terms = [t for t in phenotype_terms if t and t.strip()]
        if not phenotype_terms:
            return []
        strategy = strategy or self.default_strategy
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{strategy}'. Choose from {STRATEGIES}.")
        n_total = self.store.disease_index.ntotal
        top_k = min(top_k, n_total)

        if strategy == "concat_text":
            qv = self._encode([" ".join(phenotype_terms)])
            scores, idx = self.search_vector(qv[0], top_k)
            order, rank_scores = list(idx), {int(i): float(s) for i, s in zip(idx, scores)}
            mean_cos = rank_scores
        else:
            qvecs = self._encode(phenotype_terms)                                  # (n, d)
            mean_q = qvecs.mean(axis=0, keepdims=True)
            faiss.normalize_L2(mean_q)
            if strategy == "mean_vector":
                scores, idx = self.search_vector(mean_q[0], top_k)
                order, rank_scores = list(idx), {int(i): float(s) for i, s in zip(idx, scores)}
            elif strategy in ("hpo_expansion", "hpo_expansion_sym"):
                score = self._hpo_expansion_scores(qvecs, symmetric=(strategy == "hpo_expansion_sym"))
                top = np.argsort(-score)[:top_k]
                order, rank_scores = list(top), {int(i): float(score[i]) for i in top}
            else:  # per_phenotype_rrf
                full_s, full_i = self.store.disease_index.search(np.ascontiguousarray(qvecs, dtype=np.float32), n_total)
                rrf = np.zeros(n_total, dtype=np.float64)
                for row in full_i:
                    rrf[row] += 1.0 / (self.rrf_k + np.arange(1, n_total + 1))
                top = np.argsort(-rrf)[:top_k]
                order, rank_scores = list(top), {int(i): float(rrf[i]) for i in top}
            # mean cosine to the individual phenotype vectors, computed exactly from the index
            mean_cos = {}
            for i in order:
                dv = self.store.disease_index.reconstruct(int(i))
                mean_cos[int(i)] = float(np.mean(qvecs @ dv))

        # 0-1 score handed to the Phase 3 re-ranker: cosine for cosine-ranked strategies, the sharpened
        # best-match score for hpo_expansion, and RRF scaled by its maximum possible value.
        if strategy == "per_phenotype_rrf":
            max_rrf = len(phenotype_terms) / (self.rrf_k + 1)
            norm_score = lambda v: v / max_rrf  # noqa: E731
        else:
            norm_score = lambda v: v  # noqa: E731

        input_hpo_set = set(input_hpo_ids) if input_hpo_ids else set()
        candidates = []
        for i in order:
            i = int(i)
            if i < 0:
                continue
            rec = self.store.disease_records[i]
            matched = sorted(input_hpo_set & set(rec["hpo_ids"])) if input_hpo_set else []
            overlap = (len(matched) / len(input_hpo_set)) if input_hpo_set else 0.0
            candidates.append({
                "disease_id": rec["disease_id"], "disease_name": rec["disease_name"], "source_db": rec["source_db"],
                "embedding_similarity": round(mean_cos[i], 4),
                "retrieval_score": round(rank_scores[i], 6),
                "retrieval_score_norm": round(norm_score(rank_scores[i]), 6),
                "hpo_match_score": round(overlap, 4), "phenotype_overlap": round(overlap, 4),
                "matched_hpo_ids": matched,
                "associated_phenotypes": rec["hpo_names"][:10],
                "associated_genes": rec["genes"],
                "retrieval_strategy": strategy,
            })
        return candidates


if __name__ == "__main__":
    r = DiseaseRetriever()
    for c in r.retrieve_diseases(["hypotonia", "seizure"], top_k=3):
        print(c["disease_id"], c["disease_name"], c["embedding_similarity"])
