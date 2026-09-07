import os
import json
import yaml
import numpy as np
import faiss
from pathlib import Path

def build_faiss_indices(config_path="configs/config.yaml", rebuild=False):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    embeddings_dir = Path(config["retrieval"]["embeddings_dir"])
    vector_db_dir = Path(config["retrieval"]["vector_db_dir"])
    vector_db_dir.mkdir(parents=True, exist_ok=True)

    models_config = config["retrieval"]["models"]

    for m_key in ["primary", "baseline"]:
        m_info = models_config[m_key]
        m_name = m_info["name"]
        expected_dim = m_info["dim"]

        hpo_emb_path = embeddings_dir / f"hpo_{m_key}.npy"
        disease_emb_path = embeddings_dir / f"disease_{m_key}.npy"

        hpo_idx_path = vector_db_dir / f"hpo_{m_key}.index"
        disease_idx_path = vector_db_dir / f"disease_{m_key}.index"

        if hpo_idx_path.exists() and disease_idx_path.exists() and not rebuild:
            print(f"FAISS indices for {m_name} already exist at {vector_db_dir}. Skipping (use rebuild=True to overwrite).")
            continue

        if not hpo_emb_path.exists() or not disease_emb_path.exists():
            raise FileNotFoundError(f"Embeddings for {m_name} not found at {embeddings_dir}. Run embed_knowledge_base.py first.")

        print(f"\n--- Building FAISS Vector Index for {m_name} ---")

        # Load embeddings (already L2-normalized)
        hpo_vecs = np.load(hpo_emb_path).astype(np.float32)
        disease_vecs = np.load(disease_emb_path).astype(np.float32)

        # Normalize if needed
        faiss.normalize_L2(hpo_vecs)
        faiss.normalize_L2(disease_vecs)

        dim_hpo = hpo_vecs.shape[1]
        dim_disease = disease_vecs.shape[1]

        # Build IndexFlatIP (Cosine Similarity via Inner Product)
        index_hpo = faiss.IndexFlatIP(dim_hpo)
        index_hpo.add(hpo_vecs)

        index_disease = faiss.IndexFlatIP(dim_disease)
        index_disease.add(disease_vecs)

        faiss.write_index(index_hpo, str(hpo_idx_path))
        faiss.write_index(index_disease, str(disease_idx_path))

        print(f"Saved FAISS HPO Index ({m_name}):")
        print(f"  Vectors: {index_hpo.ntotal} | Dim: {dim_hpo} | Type: IndexFlatIP (Cosine Similarity) -> {hpo_idx_path}")

        print(f"Saved FAISS Disease Index ({m_name}):")
        print(f"  Vectors: {index_disease.ntotal} | Dim: {dim_disease} | Type: IndexFlatIP (Cosine Similarity) -> {disease_idx_path}")

    return True

if __name__ == "__main__":
    build_faiss_indices()
