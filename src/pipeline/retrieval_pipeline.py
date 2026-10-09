"""The ONE retrieval pipeline:

    clinical text -> BiomedBERT NER -> HPO normalisation -> real embeddings -> FAISS -> candidates

Every consumer (/api/retrieve, /api/diagnose, /api/rank, counterfactual) goes through this class;
there is no second phenotype-extraction path.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

sys.path.append(os.path.abspath("."))

from src.inference.predict import get_ner
from src.knowledge.hpo_normalizer import HPONormalizer
from src.rag.context_builder import build_rag_context
from src.retrieval.disease_retriever import DiseaseRetriever
from src.retrieval.store import get_store


class Phase2RetrievalPipeline:
    def __init__(self, model_key="primary", config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        ner_dir = Path(self.config["models"]["primary"]["save_dir"])
        if not ner_dir.exists():
            raise FileNotFoundError(f"BiomedBERT NER model not found at {ner_dir}.")
        self.model_key = model_key
        self.ner = get_ner(str(ner_dir))
        store = get_store(model_key, config_path)
        self.retriever = DiseaseRetriever(model_key=model_key, config_path=config_path, store=store)
        # the normaliser always uses the primary (S-PubMedBERT) HPO index
        self.normalizer = HPONormalizer(config_path, use_semantic=True, model_key="primary")
        self.candidate_pool = int(self.config["retrieval"].get("candidate_pool", 50))

    # ---- stages --------------------------------------------------------------------------
    def extract_and_map(self, clinical_text):
        mentions = self.ner.extract(clinical_text)
        mappings = self.normalizer.normalize_many([m["mention"] for m in mentions]) if mentions else []
        phenotypes, hpo_mappings, hpo_terms, unmatched, seen = [], [], [], [], set()
        for m, r in zip(mentions, mappings):
            entry = {**m, "mapping_status": r["status"], "hpo_id": r["hpo_id"], "hpo_term": r["term"],
                     "mapping_score": r["score"], "matching_method": r["matching_method"]}
            phenotypes.append(entry)
            hpo_mappings.append({**r, "mention": m["mention"], "start": m["start"], "end": m["end"],
                                 "ner_confidence": m["confidence"]})
            if r["status"] in ("exact", "synonym", "lexical", "semantic") and not r.get("is_phenotypic", True):
                entry["mapping_status"] = "non_phenotype"      # e.g. HPO modifier terms such as 'Recurrent'
                unmatched.append({"mention": m["mention"], "status": "non_phenotype", "hpo_id": r["hpo_id"], "term": r["term"],
                                  "candidates": [], "suggestions": []})
            elif r["status"] in ("exact", "synonym", "lexical", "semantic"):
                if r["hpo_id"] not in seen:
                    seen.add(r["hpo_id"])
                    hpo_terms.append({"hpo_id": r["hpo_id"], "name": r["term"], "score": r["score"],
                                      "matching_method": r["matching_method"], "status": r["status"],
                                      "mention": m["mention"]})
            else:
                unmatched.append({"mention": m["mention"], "status": r["status"],
                                  "candidates": r.get("candidates", []), "suggestions": r.get("suggestions", [])})
        return phenotypes, hpo_mappings, hpo_terms, unmatched

    def retrieve(self, hpo_terms, top_k=10, strategy=None):
        if not hpo_terms:
            return []
        return self.retriever.retrieve_diseases(
            phenotype_terms=[h["name"] for h in hpo_terms],
            input_hpo_ids=[h["hpo_id"] for h in hpo_terms],
            top_k=top_k, strategy=strategy,
        )

    # ---- entry points --------------------------------------------------------------------
    def run(self, clinical_text, top_k_disease=10, strategy=None):
        t0 = time.time()
        phenotypes, hpo_mappings, hpo_terms, unmatched = self.extract_and_map(clinical_text)
        t_map = time.time()
        candidates = self.retrieve(hpo_terms, top_k_disease, strategy)
        t_end = time.time()
        return {
            "input_text": clinical_text,
            "phenotypes": phenotypes,
            "hpo_mappings": hpo_mappings,
            "hpo_terms": hpo_terms,
            "unmatched_phenotypes": unmatched,
            "candidate_diseases": candidates,
            "rag_context": build_rag_context(clinical_text, phenotypes, hpo_terms, candidates),
            "retrieval_metadata": {
                **self.retriever.info, "top_k": top_k_disease,
                "strategy": strategy or self.retriever.default_strategy,
                "ner_model": "BiomedBERT (models/biomedbert_phenotype_ner)",
                "n_mentions": len(phenotypes), "n_mapped_hpo_terms": len(hpo_terms), "n_unmatched": len(unmatched),
                "note": None if hpo_terms else "No phenotype could be mapped to an HPO term; no retrieval was performed.",
                "latency_ms": {"ner_and_mapping": round((t_map - t0) * 1000, 1), "retrieval": round((t_end - t_map) * 1000, 1)},
            },
        }

    def run_from_hpo_terms(self, hpo_terms, top_k_disease=10, strategy=None):
        """Retrieval for an explicit (already normalised) HPO term set - used by counterfactual analysis."""
        candidates = self.retrieve(hpo_terms, top_k_disease, strategy)
        return {"hpo_terms": hpo_terms, "candidate_diseases": candidates}


def main():
    parser = argparse.ArgumentParser(description="Phase 2R retrieval pipeline")
    parser.add_argument("--text", type=str, required=True)
    parser.add_argument("--model-key", default="primary", choices=["primary", "baseline"])
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--strategy", default=None, choices=["mean_vector", "per_phenotype_rrf", "concat_text"])
    args = parser.parse_args()
    res = Phase2RetrievalPipeline(model_key=args.model_key).run(args.text, args.top_k, args.strategy)
    res.pop("rag_context")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
