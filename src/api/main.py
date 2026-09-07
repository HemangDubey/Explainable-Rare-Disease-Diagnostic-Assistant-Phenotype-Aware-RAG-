import os
import sys
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

sys.path.append(os.path.abspath("."))

from src.pipeline.retrieval_pipeline import Phase2RetrievalPipeline
from src.pipeline.ranking_pipeline import Phase3RankingPipeline

app = FastAPI(
    title="Explainable Rare-Disease Diagnostic Assistant API",
    description="Phenotype-Aware RAG with Indian Population Priors (Phase 2 Retrieval + Phase 3 Population Re-ranking)",
    version="3.0.0"
)

# Global pipeline instances
retrieval_pipeline = None
ranking_pipeline = None

@app.on_event("startup")
def startup_event():
    global retrieval_pipeline, ranking_pipeline
    print("Initializing Phase 2 & Phase 3 Pipelines...")
    retrieval_pipeline = Phase2RetrievalPipeline(model_key="primary")
    ranking_pipeline = Phase3RankingPipeline(model_key="primary")
    print("Pipelines initialized successfully.")

class ClinicalTextRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    top_k: Optional[int] = Field(default=10, example=10)
    strategy: Optional[str] = Field(default="mean_vector", example="mean_vector")

class RankRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    top_k: Optional[int] = Field(default=10, example=10)
    exp_config: Optional[str] = Field(default="rag_indigen_gnomad", example="rag_indigen_gnomad")

class RetrievalResponse(BaseModel):
    input_text: str
    phenotypes: List[Dict[str, Any]]
    hpo_terms: List[Dict[str, Any]]
    candidate_diseases: List[Dict[str, Any]]
    rag_context: Dict[str, Any]

class RankResponse(BaseModel):
    phenotypes: List[Dict[str, Any]]
    hpo_terms: List[Dict[str, Any]]
    retrieved_candidates: List[Dict[str, Any]]
    ranked_candidates: List[Dict[str, Any]]
    ranking_explanations: List[str]

@app.get("/")
def health_check():
    return {
        "service": "Explainable Rare-Disease Diagnostic Assistant API",
        "phase": 3,
        "status": "healthy"
    }

@app.post("/api/retrieve", response_model=RetrievalResponse)
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
        raise HTTPException(status_code=500, detail=f"Retrieval error: {str(e)}")

@app.post("/api/rank", response_model=RankResponse)
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
        raise HTTPException(status_code=500, detail=f"Ranking error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
