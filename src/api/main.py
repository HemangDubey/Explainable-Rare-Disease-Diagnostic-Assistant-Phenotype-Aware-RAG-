import os
import sys
import yaml
import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

sys.path.append(os.path.abspath("."))

from src.pipeline.retrieval_pipeline import Phase2RetrievalPipeline
from src.pipeline.ranking_pipeline import Phase3RankingPipeline
from src.reasoning.evidence_fusion import EvidenceFusionEngine
from src.reasoning.llm_reasoner import LLMReasoner
from src.reasoning.differential import DifferentialEngine
from src.reasoning.copilot import DoctorCopilot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostic_api")

app = FastAPI(
    title="Explainable Rare-Disease Diagnostic Assistant API",
    description="Phenotype-Aware RAG with Indian Population Priors & LLM Clinical Reasoning (Phases 1–4)",
    version="4.0.0"
)

# Enable CORS for React Vite frontend (port 5173, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline & reasoning instances
config = {}
retrieval_pipeline = None
ranking_pipeline = None
fusion_engine = None
llm_reasoner = None
differential_engine = None
doctor_copilot = None

# In-memory case context session store for persistent navigation
case_store: Dict[str, Dict[str, Any]] = {}

@app.on_event("startup")
def startup_event():
    global config, retrieval_pipeline, ranking_pipeline, fusion_engine, llm_reasoner, differential_engine, doctor_copilot
    config_path = "configs/config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("Initializing Phase 1-3 Pipelines...")
    retrieval_pipeline = Phase2RetrievalPipeline(model_key="primary", config_path=config_path)
    ranking_pipeline = Phase3RankingPipeline(model_key="primary", config_path=config_path)

    logger.info("Initializing Phase 4 Reasoning & Evidence Engines...")
    fusion_engine = EvidenceFusionEngine(config=config)
    llm_reasoner = LLMReasoner(config=config)
    differential_engine = DifferentialEngine(config=config)
    doctor_copilot = DoctorCopilot(config=config)
    logger.info("All pipelines & reasoning engines initialized successfully.")

# Request / Response Schemas
class ClinicalTextRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    top_k: Optional[int] = Field(default=10, example=10)
    strategy: Optional[str] = Field(default="mean_vector", example="mean_vector")

class RankRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    top_k: Optional[int] = Field(default=10, example=10)
    exp_config: Optional[str] = Field(default="rag_indigen_gnomad", example="rag_indigen_gnomad")

class DiagnoseRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    top_k: Optional[int] = Field(default=5, example=5)
    exp_config: Optional[str] = Field(default="rag_indigen_gnomad", example="rag_indigen_gnomad")
    case_id: Optional[str] = Field(default=None, example=None)

class ExplainRequest(BaseModel):
    case_id: Optional[str] = Field(default=None)
    disease_id: str = Field(..., example="OMIM:620790")
    clinical_text: Optional[str] = Field(default="")

class DifferentialRequest(BaseModel):
    case_id: Optional[str] = Field(default=None)
    clinical_text: Optional[str] = Field(default="")
    top_k: Optional[int] = Field(default=5)

class CopilotRequest(BaseModel):
    query: str = Field(..., example="Why was this disease prioritized over other candidates?")
    case_id: Optional[str] = Field(default=None)
    clinical_text: Optional[str] = Field(default="")

# Endpoints
@app.get("/")
def health_check():
    provider_health = llm_reasoner.provider.check_health() if llm_reasoner else {}
    return {
        "service": "Explainable Rare-Disease Diagnostic Assistant API",
        "version": "4.0.0",
        "phase": 4,
        "status": "healthy",
        "llm": provider_health
    }

@app.post("/api/retrieve")
def retrieve_endpoint(request: ClinicalTextRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text observation must not be empty.")

    try:
        results = retrieval_pipeline.run(
            clinical_text=request.text,
            top_k_disease=request.top_k or 10,
            strategy=request.strategy or "mean_vector"
        )
        return results
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval error: {str(e)}")

@app.post("/api/rank")
def rank_endpoint(request: RankRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text observation must not be empty.")

    try:
        results = ranking_pipeline.run(
            clinical_text=request.text,
            top_k_disease=request.top_k or 10,
            exp_config=request.exp_config or "rag_indigen_gnomad"
        )
        return {
            "phenotypes": results["phenotypes"],
            "hpo_terms": results["hpo_terms"],
            "retrieved_candidates": results["retrieved_candidates"],
            "ranked_candidates": results["ranked_candidates"],
            "ranking_explanations": results["ranking_explanations"]
        }
    except Exception as e:
        logger.error(f"Ranking error: {e}")
        raise HTTPException(status_code=500, detail=f"Ranking error: {str(e)}")

@app.post("/api/diagnose")
def diagnose_endpoint(request: DiagnoseRequest):
    """
    End-to-End Diagnostic Pipeline (Phases 1 → 2 → 3 → 4):
    Clinical Text -> BiomedBERT NER -> HPO Normalization -> FAISS Retrieval ->
    IndiGen / gnomAD Re-ranking -> Evidence Fusion -> LLM Clinical Reasoning -> Differential Analysis.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Clinical case text must not be empty.")

    try:
        case_id = request.case_id or str(uuid.uuid4())[:8]

        # 1. Execute Phase 3 Ranking Pipeline (contains Phase 1 NER, Phase 2 FAISS, Phase 3 Priors)
        p3_results = ranking_pipeline.run(
            clinical_text=request.text,
            top_k_disease=request.top_k or 5,
            exp_config=request.exp_config or "rag_indigen_gnomad"
        )

        extracted_phenotypes = p3_results.get("phenotypes", [])
        hpo_terms = p3_results.get("hpo_terms", [])
        ranked_candidates = p3_results.get("ranked_candidates", [])

        # 2. Phase 4 Evidence Fusion
        fused_candidates = fusion_engine.fuse_all_candidates(
            ranked_candidates=ranked_candidates,
            extracted_phenotypes=extracted_phenotypes,
            hpo_terms=hpo_terms,
            top_k=request.top_k or 5
        )

        # 3. Phase 4 Top Candidate LLM Reasoning Explanation
        top_explanation = None
        if fused_candidates:
            top_explanation = llm_reasoner.explain_candidate(
                candidate_evidence=fused_candidates[0],
                clinical_case_text=request.text
            )

        # 4. Phase 4 Differential Diagnosis Synthesis
        differential = differential_engine.generate_differential(
            fused_candidates=fused_candidates,
            clinical_case_text=request.text
        )

        # Store in case context session store
        case_context = {
            "case_id": case_id,
            "clinical_text": request.text,
            "extracted_phenotypes": extracted_phenotypes,
            "hpo_terms": hpo_terms,
            "ranked_candidates": ranked_candidates,
            "fused_candidates": fused_candidates,
            "top_explanation": top_explanation,
            "differential": differential
        }
        case_store[case_id] = case_context

        return {
            "case_id": case_id,
            "clinical_text": request.text,
            "extracted_phenotypes": extracted_phenotypes,
            "hpo_terms": hpo_terms,
            "fused_candidates": fused_candidates,
            "top_explanation": top_explanation,
            "differential": differential,
            "disclaimer": "Prioritized candidates are clinical decision-support recommendations and do NOT constitute confirmed diagnoses. Genetic confirmation and specialist evaluation are required."
        }
    except Exception as e:
        logger.error(f"Diagnose pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostic pipeline error: {str(e)}")

@app.post("/api/explain")
def explain_endpoint(request: ExplainRequest):
    """
    Generates an evidence-grounded LLM explanation for any specific candidate disease.
    """
    case_context = case_store.get(request.case_id) if request.case_id else None
    
    if not case_context:
        # If no case_id in store, run on-the-fly ranking
        if not request.clinical_text:
            raise HTTPException(status_code=400, detail="Either a valid case_id or clinical_text must be provided.")
        p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=5)
        fused = fusion_engine.fuse_all_candidates(
            p3_res["ranked_candidates"],
            p3_res["phenotypes"],
            p3_res["hpo_terms"],
            top_k=5
        )
        case_context = {
            "clinical_text": request.clinical_text,
            "fused_candidates": fused
        }

    # Find the target candidate
    target_cand = None
    for cand in case_context.get("fused_candidates", []):
        if cand.get("disease_id") == request.disease_id or cand.get("disease_name") == request.disease_id:
            target_cand = cand
            break

    if not target_cand and case_context.get("fused_candidates"):
        target_cand = case_context["fused_candidates"][0]

    if not target_cand:
        raise HTTPException(status_code=404, detail="Candidate disease not found in current case.")

    explanation = llm_reasoner.explain_candidate(
        candidate_evidence=target_cand,
        clinical_case_text=case_context.get("clinical_text", "")
    )
    return explanation

@app.post("/api/differential")
def differential_endpoint(request: DifferentialRequest):
    """
    Compares prioritized candidate diseases side-by-side.
    """
    case_context = case_store.get(request.case_id) if request.case_id else None
    if not case_context:
        if not request.clinical_text:
            raise HTTPException(status_code=400, detail="Either a valid case_id or clinical_text must be provided.")
        p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=request.top_k or 5)
        fused = fusion_engine.fuse_all_candidates(
            p3_res["ranked_candidates"],
            p3_res["phenotypes"],
            p3_res["hpo_terms"],
            top_k=request.top_k or 5
        )
        diff = differential_engine.generate_differential(fused, request.clinical_text)
        return diff

    return case_context.get("differential", {})

@app.post("/api/copilot")
def copilot_endpoint(request: CopilotRequest):
    """
    Interactive Q&A with the Explainable AI Doctor Copilot for the current case.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    case_context = case_store.get(request.case_id) if request.case_id else None
    if not case_context:
        if request.clinical_text and request.clinical_text.strip():
            p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=5)
            fused = fusion_engine.fuse_all_candidates(
                p3_res["ranked_candidates"],
                p3_res["phenotypes"],
                p3_res["hpo_terms"],
                top_k=5
            )
            case_context = {
                "clinical_text": request.clinical_text,
                "extracted_phenotypes": p3_res.get("phenotypes", []),
                "hpo_terms": p3_res.get("hpo_terms", []),
                "fused_candidates": fused
            }
        else:
            case_context = {
                "clinical_text": "General inquiry without active case.",
                "extracted_phenotypes": [],
                "hpo_terms": [],
                "fused_candidates": []
            }

    response = doctor_copilot.answer_query(
        query=request.query,
        case_context=case_context
    )
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
