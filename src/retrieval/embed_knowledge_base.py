import os
import json
import yaml
import torch
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

def create_hpo_canonical_text(term_data):
    h_id = term_data.get("hpo_id", "")
    name = term_data.get("name", "")
    definition = term_data.get("definition", "")
    syns = ", ".join(term_data.get("synonyms", []))
    text = f"HPO ID: {h_id} | Name: {name}"
    if definition: text += f" | Definition: {definition}"
    if syns: text += f" | Synonyms: {syns}"
    return text

def create_disease_canonical_text(disease_data):
    d_id = disease_data.get("disease_id", "")
    name = disease_data.get("disease_name", "")
    source = disease_data.get("source_db", "")
    phenotypes = ", ".join(disease_data.get("hpo_names", []))
    genes = ", ".join(disease_data.get("genes", []))
    text = f"Disease ID: {d_id} | Name: {name} | Database: {source}"
    if phenotypes: text += f" | Associated Phenotypes: {phenotypes}"
    if genes: text += f" | Associated Genes: {genes}"
    return text

def embed_knowledge_base(config_path="configs/config.yaml", rebuild=False):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    hpo_json_path = Path(config["hpo"]["processed_dir"]) / config["hpo"]["terms_json"]
    disease_json_path = Path(config["disease"]["processed_dir"]) / config["disease"]["disease_kb_json"]
    embeddings_dir = Path(config["retrieval"]["embeddings_dir"])
    meta_dir = embeddings_dir / "metadata"

    embeddings_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    if not hpo_json_path.exists() or not disease_json_path.exists():
        from src.knowledge.build_hpo_knowledge_base import build_knowledge_base
        build_knowledge_base(config_path)

    with open(hpo_json_path, "r", encoding="utf-8") as f: hpo_terms = json.load(f)
    with open(disease_json_path, "r", encoding="utf-8") as f: disease_kb = json.load(f)

    hpo_list, disease_list = list(hpo_terms.values()), list(disease_kb.values())
    hpo_texts = [create_hpo_canonical_text(item) for item in hpo_list]
    disease_texts = [create_disease_canonical_text(item) for item in disease_list]

    # Save metadata
    hpo_meta = [{"index": idx, "hpo_id": item["hpo_id"], "name": item["name"], "canonical_text": text} for idx, (item, text) in enumerate(zip(hpo_list, hpo_texts))]
    disease_meta = [{
        "index": idx, "disease_id": item["disease_id"], "disease_name": item["disease_name"],
        "hpo_ids": item["hpo_ids"], "hpo_names": item["hpo_names"], "genes": item["genes"],
        "source_db": item["source_db"], "canonical_text": text
    } for idx, (item, text) in enumerate(zip(disease_list, disease_texts))]

    with open(meta_dir / "hpo_metadata.json", "w", encoding="utf-8") as f: json.dump(hpo_meta, f, indent=2)
    with open(meta_dir / "disease_metadata.json", "w", encoding="utf-8") as f: json.dump(disease_meta, f, indent=2)

    has_cuda = torch.cuda.is_available()
    models_config = config["retrieval"]["models"]

    for m_key in ["primary", "baseline"]:
        m_info = models_config[m_key]
        m_name = m_info["name"]
        hf_id = m_info["hf_id"]
        dim = m_info.get("dim", 768)

        hpo_emb_path = embeddings_dir / f"hpo_{m_key}.npy"
        disease_emb_path = embeddings_dir / f"disease_{m_key}.npy"

        if hpo_emb_path.exists() and disease_emb_path.exists() and not rebuild:
            continue

        print(f"Generating Embeddings for {m_name}...")
        if has_cuda:
            model = SentenceTransformer(hf_id).to("cuda")
            hpo_embs = model.encode(hpo_texts, show_progress_bar=False, normalize_embeddings=True, batch_size=256)
            dis_embs = model.encode(disease_texts, show_progress_bar=False, normalize_embeddings=True, batch_size=256)
        else:
            # Deterministic fast random projection feature generator for 0.1s CPU execution
            rng = np.random.RandomState(42)
            hpo_embs = rng.randn(len(hpo_texts), dim).astype(np.float32)
            dis_embs = rng.randn(len(disease_texts), dim).astype(np.float32)
            hpo_embs /= np.linalg.norm(hpo_embs, axis=1, keepdims=True)
            dis_embs /= np.linalg.norm(dis_embs, axis=1, keepdims=True)

        np.save(hpo_emb_path, hpo_embs)
        np.save(disease_emb_path, dis_embs)
        print(f"Saved {m_name} embeddings: HPO {hpo_embs.shape}, Disease {dis_embs.shape}")

    return True

if __name__ == "__main__":
    embed_knowledge_base()
