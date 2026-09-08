import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.knowledge.hpo_normalizer import HPONormalizer
from src.counterfactual.schemas import (
    CounterfactualRequest,
    CounterfactualResponse,
    CounterfactualExperimentRecord,
    CandidateRankDelta,
    PhenotypeImpactItem
)
from src.counterfactual.ranking_delta import compute_ranking_deltas
from src.counterfactual.phenotype_impact import calculate_phenotype_impacts
from src.counterfactual.what_if_analysis import generate_counterfactual_insights

logger = logging.getLogger("counterfactual_engine")

class CounterfactualEngine:
    def __init__(self, ranking_pipeline, config_path="configs/config.yaml"):
        self.ranking_pipeline = ranking_pipeline
        self.normalizer = HPONormalizer(config_path=config_path)
        self.experiment_store: Dict[str, Dict[str, Any]] = {}

    def run_analysis(
        self,
        request: CounterfactualRequest,
        case_store: Dict[str, Dict[str, Any]]
    ) -> CounterfactualResponse:
        cid = request.case_id or "default_case"
        case_ctx = case_store.get(cid)

        # Baseline setup
        if case_ctx and case_ctx.get("ranked_candidates"):
            baseline_text = case_ctx.get("clinical_text", "")
            baseline_hpos = case_ctx.get("hpo_terms", [])
            baseline_ranked = case_ctx.get("ranked_candidates", [])
        else:
            baseline_text = (case_ctx.get("clinical_text") if case_ctx else request.clinical_text) or "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
            p3_base = self.ranking_pipeline.run(
                clinical_text=baseline_text,
                top_k_disease=request.top_k or 5,
                exp_config=request.exp_config or "rag_indigen_gnomad"
            )
            baseline_hpos = case_ctx.get("hpo_terms") if case_ctx and case_ctx.get("hpo_terms") else p3_base.get("hpo_terms", [])
            baseline_ranked = p3_base.get("ranked_candidates", [])

        # Build active list of phenotype terms for modification
        baseline_hpo_ids = [h.get("hpo_id") for h in baseline_hpos if h.get("hpo_id")]
        baseline_hpo_names = [h.get("name") for h in baseline_hpos if h.get("name")]

        modified_hpos = list(baseline_hpos)
        target_term_label = ""

        op = request.operation.lower()

        # Handle ADD operation
        if op == "add":
            terms_to_add = request.added_phenotypes or []
            if request.phenotype_id:
                terms_to_add.append(request.phenotype_id)
            
            target_term_label = ", ".join(terms_to_add)
            for t_add in terms_to_add:
                # Normalize if string term or HPO ID
                norm_res = self.normalizer.normalize(t_add, top_k=1)
                if norm_res:
                    best = norm_res[0]
                    if best["hpo_id"] not in [h.get("hpo_id") for h in modified_hpos]:
                        modified_hpos.append(best)
                else:
                    modified_hpos.append({"hpo_id": t_add, "name": t_add, "score": 1.0})

        # Handle REMOVE operation
        elif op == "remove":
            terms_to_remove = request.removed_phenotypes or []
            if request.phenotype_id:
                terms_to_remove.append(request.phenotype_id)
            
            target_term_label = ", ".join(terms_to_remove)
            terms_to_remove_clean = [t.strip().lower() for t in terms_to_remove]
            
            modified_hpos = [
                h for h in modified_hpos
                if h.get("hpo_id", "").lower() not in terms_to_remove_clean
                and h.get("name", "").lower() not in terms_to_remove_clean
            ]

        # Handle TOGGLE operation
        elif op == "toggle":
            t_target = (request.phenotype_id or "").strip()
            target_term_label = t_target
            t_target_lower = t_target.lower()
            
            is_present = any(
                h.get("hpo_id", "").lower() == t_target_lower or h.get("name", "").lower() == t_target_lower
                for h in modified_hpos
            )
            
            if is_present:
                modified_hpos = [
                    h for h in modified_hpos
                    if h.get("hpo_id", "").lower() != t_target_lower
                    and h.get("name", "").lower() != t_target_lower
                ]
            else:
                norm_res = self.normalizer.normalize(t_target, top_k=1)
                if norm_res:
                    modified_hpos.append(norm_res[0])
                else:
                    modified_hpos.append({"hpo_id": t_target, "name": t_target, "score": 1.0})

        # Handle COMPARE / CUSTOM STATE operation
        elif op == "compare":
            custom_terms = request.modified_phenotypes or []
            target_term_label = ", ".join(custom_terms)
            modified_hpos = []
            for ct in custom_terms:
                norm_res = self.normalizer.normalize(ct, top_k=1)
                if norm_res:
                    modified_hpos.append(norm_res[0])
                else:
                    modified_hpos.append({"hpo_id": ct, "name": ct, "score": 1.0})

        # Construct modified clinical text query for pipeline execution
        modified_phenotype_names = [h.get("name", h.get("hpo_id")) for h in modified_hpos]
        if modified_phenotype_names:
            modified_text = "Patient presents with " + ", ".join(modified_phenotype_names)
        else:
            modified_text = "Patient presents with non-specific observations."

        # Rerun Phase 3 ranking pipeline on modified phenotype set
        p3_counterfactual = self.ranking_pipeline.run(
            clinical_text=modified_text,
            top_k_disease=request.top_k or 5,
            exp_config=request.exp_config or "rag_indigen_gnomad"
        )
        cf_ranked = p3_counterfactual.get("ranked_candidates", [])

        # Compute Ranking Deltas & Score Sensitivity
        ranking_deltas = compute_ranking_deltas(
            baseline_ranked=baseline_ranked,
            counterfactual_ranked=cf_ranked
        )

        def run_pipeline_for_ablation(text_query, top_k_disease):
            return self.ranking_pipeline.run(
                clinical_text=text_query,
                top_k_disease=top_k_disease,
                exp_config=request.exp_config or "rag_indigen_gnomad"
            )

        phenotype_impacts = calculate_phenotype_impacts(
            baseline_hpos=baseline_hpos,
            baseline_ranked=baseline_ranked,
            ranking_pipeline_fn=run_pipeline_for_ablation
        )

        insights = generate_counterfactual_insights(
            operation=op,
            target_phenotype=target_term_label,
            deltas=ranking_deltas,
            impacts=phenotype_impacts
        )

        exp_id = f"exp_{str(uuid.uuid4())[:8]}"

        response = CounterfactualResponse(
            experiment_id=exp_id,
            case_id=cid,
            operation=op,
            baseline_phenotypes=baseline_hpos,
            modified_phenotypes=modified_hpos,
            baseline_ranking=baseline_ranked,
            counterfactual_ranking=cf_ranked,
            ranking_deltas=ranking_deltas,
            phenotype_impacts=phenotype_impacts,
            insights=insights
        )

        # Store experiment record in history
        self.experiment_store[exp_id] = {
            "experiment_id": exp_id,
            "case_id": cid,
            "operation": op,
            "timestamp": datetime.now().isoformat(),
            "baseline_phenotypes": baseline_hpos,
            "modified_phenotypes": modified_hpos,
            "response": response.model_dump() if hasattr(response, "model_dump") else response.dict()
        }

        return response

    def get_case_experiments(self, case_id: str) -> List[Dict[str, Any]]:
        return [
            exp["response"] for exp in self.experiment_store.values()
            if exp.get("case_id") == case_id
        ]
