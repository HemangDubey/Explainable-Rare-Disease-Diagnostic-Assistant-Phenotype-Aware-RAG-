import os
import sys
import json
import yaml
import argparse
from pathlib import Path

sys.path.append(os.path.abspath("."))
from src.knowledge.hpo_normalizer import HPONormalizer
from src.retrieval.disease_retriever import DiseaseRetriever
from src.ranking.disease_ranker import DiseaseRanker
from src.ranking.explanation import generate_ranking_explanation
from src.rag.context_builder import build_rag_context

class Phase3RankingPipeline:
    def __init__(self, model_key="primary", config_path="configs/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.normalizer = HPONormalizer(config_path)
        self.disease_retriever = DiseaseRetriever(model_key=model_key, config_path=config_path)
        self.disease_ranker = DiseaseRanker(config_path=config_path)

    def run(self, clinical_text, top_k_disease=10, exp_config="rag_indigen_gnomad"):
        # 1. Phenotype Extraction (NER mention fallback / Phase 1 integration)
        phenotype_mentions = [p.strip() for p in clinical_text.replace("Patient presents with", "").replace("and", ",").split(",") if p.strip()]
        extracted_mentions = [{"phenotype": p, "span": "N/A"} for p in phenotype_mentions]

        # 2. HPO Normalization
        hpo_mappings, input_hpo_ids = [], []
        for text_m in phenotype_mentions:
            norm_c = self.normalizer.normalize(text_m, top_k=1)
            if norm_c:
                best = norm_c[0]
                hpo_mappings.append(best)
                input_hpo_ids.append(best["hpo_id"])

        # 3. Dense FAISS Semantic Retrieval (Phase 2 candidates)
        retrieved_candidates = self.disease_retriever.retrieve_diseases(
            phenotype_terms=phenotype_mentions, input_hpo_ids=input_hpo_ids, top_k=top_k_disease
        )

        # 4. Population Prior Re-ranking (Phase 3)
        ranked_candidates = self.disease_ranker.rank_candidates(
            retrieved_candidates, exp_config=exp_config
        )

        # 5. Clinical Explainability Rationale
        ranking_explanations = [generate_ranking_explanation(cand) for cand in ranked_candidates]

        # 6. Structured RAG Context Assembly
        rag_context = build_rag_context(clinical_text, extracted_mentions, hpo_mappings, ranked_candidates)

        return {
            "input_text": clinical_text,
            "phenotypes": extracted_mentions,
            "hpo_terms": hpo_mappings,
            "retrieved_candidates": retrieved_candidates,
            "ranked_candidates": ranked_candidates,
            "ranking_explanations": ranking_explanations,
            "rag_context": rag_context
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    args = parser.parse_args()

    p = Phase3RankingPipeline()
    res = p.run(args.text)
    print(json.dumps({
        "input_text": res["input_text"],
        "top_ranked_candidate": res["ranked_candidates"][0] if res["ranked_candidates"] else None,
        "sample_explanation": res["ranking_explanations"][0] if res["ranking_explanations"] else None
    }, indent=2))
