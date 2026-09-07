import os
import sys
import json
import yaml
import argparse
from pathlib import Path

# Add workspace root to sys.path
sys.path.append(os.path.abspath("."))

from src.inference.predict import predict_phenotypes
from src.knowledge.hpo_normalizer import HPONormalizer
from src.retrieval.disease_retriever import DiseaseRetriever
from src.rag.context_builder import build_rag_context

class Phase2RetrievalPipeline:
    def __init__(self, model_key="primary", config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.model_key = model_key
        ner_model_dir = Path(self.config["models"]["primary"]["save_dir"])
        if not ner_model_dir.exists():
            raise FileNotFoundError(f"Phase 1 BiomedBERT model not found at {ner_model_dir}.")

        self.ner_model_dir = str(ner_model_dir)
        self.normalizer = HPONormalizer(config_path)
        self.disease_retriever = DiseaseRetriever(model_key=model_key, config_path=config_path)

    def run(self, clinical_text, top_k_disease=10, strategy="mean_vector"):
        # Step 1: Extract Phenotype Mentions using Phase 1 BiomedBERT NER
        extracted_mentions = predict_phenotypes(self.ner_model_dir, clinical_text)

        raw_phenotype_texts = [item["phenotype"] for item in extracted_mentions]

        # Step 2: HPO Normalization
        hpo_mappings = []
        input_hpo_ids = []
        for text_mention in raw_phenotype_texts:
            norm_candidates = self.normalizer.normalize(text_mention, top_k=1)
            if norm_candidates:
                best_match = norm_candidates[0]
                hpo_mappings.append(best_match)
                input_hpo_ids.append(best_match["hpo_id"])

        # Step 3: Disease Candidate Semantic Retrieval via FAISS
        disease_candidates = self.disease_retriever.retrieve_diseases(
            phenotype_terms=raw_phenotype_texts if raw_phenotype_texts else [clinical_text],
            input_hpo_ids=input_hpo_ids,
            top_k=top_k_disease,
            strategy=strategy
        )

        # Step 4: Build Structured RAG Context Block
        rag_context = build_rag_context(
            clinical_text=clinical_text,
            extracted_phenotypes=extracted_mentions,
            hpo_mappings=hpo_mappings,
            candidate_diseases=disease_candidates
        )

        return {
            "input_text": clinical_text,
            "phenotypes": extracted_mentions,
            "hpo_terms": hpo_mappings,
            "candidate_diseases": disease_candidates,
            "rag_context": rag_context
        }

def main():
    parser = argparse.ArgumentParser(description="Phase 2 Retrieval Pipeline")
    parser.add_argument("--text", type=str, required=True, help="Clinical observation text")
    parser.add_argument("--model-key", type=str, default="primary", choices=["primary", "baseline"], help="Retrieval model key")
    parser.add_argument("--top-k", type=int, default=10, help="Number of candidate diseases to retrieve")
    parser.add_argument("--strategy", type=str, default="mean_vector", choices=["mean_vector", "concat_text"], help="Multi-phenotype query aggregation strategy")
    args = parser.parse_args()

    pipeline = Phase2RetrievalPipeline(model_key=args.model_key)
    result = pipeline.run(args.text, top_k_disease=args.top_k, strategy=args.strategy)

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
