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
from src.scribe.scribe_engine import ClinicalScribeEngine
from src.scribe.schemas import ScribeRequest, ScribeResponse
from src.counterfactual.counterfactual_engine import CounterfactualEngine
from src.counterfactual.schemas import CounterfactualRequest, CounterfactualResponse
from src.input_guard.input_validator import InputValidatorGuard
from src.input_guard.schemas import ValidationRequest, ValidationResponse, EnhanceRequest, EnhanceResponse

from src.literature.pubmed_client import PubMedClient
from src.literature.query_builder import PubMedQueryBuilder
from src.literature.relevance import LiteratureRelevanceScorer
from src.literature.schemas import (
    PubMedArticle, LiteratureSearchRequest, EvidenceMatrixResponse, DiseaseEvidenceProfile
)
from src.evidence.evidence_classifier import EvidenceClassifier
from src.evidence.evidence_matrix import EvidenceMatrixBuilder
from src.evidence.evidence_profile import DiseaseEvidenceProfileBuilder
from src.reporting.report_schema import ClinicalCaseReport
from src.reporting.report_generator import CaseReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostic_api")

app = FastAPI(
    title="Explainable Rare-Disease Diagnostic Assistant API",
    description="Phenotype-Aware RAG with Indian Population Priors, Explainable AI Reasoning, Counterfactual Lab & Evidence Intelligence (Phases 1–6)",
    version="6.0.0"
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
scribe_engine = None
counterfactual_engine = None
input_guard = None

# Phase 6 singletons
pubmed_client = None
relevance_scorer = None

# In-memory case context session store for persistent navigation
case_store: Dict[str, Dict[str, Any]] = {}
report_store: Dict[str, ClinicalCaseReport] = {}

@app.on_event("startup")
def startup_event():
    global config, retrieval_pipeline, ranking_pipeline, fusion_engine, llm_reasoner, differential_engine, doctor_copilot, scribe_engine, counterfactual_engine, input_guard, pubmed_client, relevance_scorer
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

    logger.info("Initializing Phase 5 Scribe & Counterfactual Engines...")
    scribe_engine = ClinicalScribeEngine(config_path=config_path)
    counterfactual_engine = CounterfactualEngine(ranking_pipeline=ranking_pipeline, config_path=config_path)

    logger.info("Initializing Input Quality Gate & AI Enhancement Guard...")
    groq_cfg = config.get("groq", {})
    input_guard = InputValidatorGuard(
        groq_api_key=groq_cfg.get("api_key"),
        groq_model=groq_cfg.get("model", "groq/compound-mini")
    )

    logger.info("Initializing Phase 6 Literature Intelligence Engines...")
    pubmed_client = PubMedClient()
    relevance_scorer = LiteratureRelevanceScorer()

    logger.info("All Phase 1-6 pipelines, reasoning & evidence intelligence engines initialized successfully.")

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

@app.post("/api/input/validate", response_model=ValidationResponse)
def validate_input_endpoint(request: ValidationRequest):
    """
    Input Quality Gate API:
    Validates clinical text for relevance, profanity/abuse, and usability.
    """
    if not input_guard:
        raise HTTPException(status_code=500, detail="Input Quality Gate engine not initialized.")
    return input_guard.validate_input(request.text)

@app.post("/api/input/enhance", response_model=EnhanceResponse)
def enhance_input_endpoint(request: EnhanceRequest):
    """
    AI Text Enhancement API:
    Normalizes phrasing, fixes grammar and clinical abbreviations using local AI without fabricating facts.
    """
    if not input_guard:
        raise HTTPException(status_code=500, detail="AI Text Enhancement engine not initialized.")
    return input_guard.enhance_text(request.text)

@app.post("/api/diagnose")
def diagnose_endpoint(request: DiagnoseRequest):
    """
    End-to-End Diagnostic Pipeline (Phases 1 → 2 → 3 → 4):
    Clinical Text -> BiomedBERT NER -> HPO Normalization -> FAISS Retrieval ->
    IndiGen / gnomAD Re-ranking -> Evidence Fusion -> LLM Clinical Reasoning -> Differential Analysis.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Clinical case text must not be empty.")

    # Quality Gate Check
    if input_guard:
        val_res = input_guard.validate_input(request.text)
        if not val_res.is_valid_clinical:
            raise HTTPException(status_code=400, detail=val_res.reason)

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

# ==========================================
# PHASE 5 API ENDPOINTS
# ==========================================

@app.post("/api/scribe", response_model=ScribeResponse)
def scribe_endpoint(request: ScribeRequest):
    """
    Phase 5 AI Clinical Scribe:
    Converts unstructured clinical text into a structured clinical case model,
    mapping phenotypes via HPO Normalization and storing case context for diagnostic pipeline execution.
    """
    if not request.clinical_text or not request.clinical_text.strip():
        raise HTTPException(status_code=400, detail="Clinical narrative text must not be empty.")

    try:
        scribe_res = scribe_engine.extract_structured_case(
            clinical_text=request.clinical_text,
            case_id=request.case_id
        )

        # Store in-memory case context
        case_store[scribe_res.case_id] = {
            "case_id": scribe_res.case_id,
            "clinical_text": request.clinical_text,
            "structured_case": scribe_res.structured_case.dict(),
            "extracted_phenotypes": scribe_res.phenotypes,
            "hpo_terms": scribe_res.hpo_terms
        }

        return scribe_res
    except Exception as e:
        logger.error(f"Scribe extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Clinical Scribe error: {str(e)}")

@app.post("/api/counterfactual", response_model=CounterfactualResponse)
def counterfactual_endpoint(request: CounterfactualRequest):
    """
    Phase 5 Counterfactual Diagnosis Lab:
    Executes controlled what-if analysis on candidate disease prioritization
    by adding, removing, or toggling phenotypes against the baseline pipeline.
    """
    try:
        cf_res = counterfactual_engine.run_analysis(
            request=request,
            case_store=case_store
        )
        return cf_res
    except Exception as e:
        logger.error(f"Counterfactual analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Counterfactual analysis error: {str(e)}")

@app.post("/api/counterfactual/add", response_model=CounterfactualResponse)
def counterfactual_add_endpoint(request: CounterfactualRequest):
    """Shortcut endpoint to add phenotypes in counterfactual analysis."""
    request.operation = "add"
    return counterfactual_endpoint(request)

@app.post("/api/counterfactual/remove", response_model=CounterfactualResponse)
def counterfactual_remove_endpoint(request: CounterfactualRequest):
    """Shortcut endpoint to remove phenotypes in counterfactual analysis."""
    request.operation = "remove"
    return counterfactual_endpoint(request)

@app.post("/api/counterfactual/compare", response_model=CounterfactualResponse)
def counterfactual_compare_endpoint(request: CounterfactualRequest):
    """Shortcut endpoint to compare two case states in counterfactual analysis."""
    request.operation = "compare"
    return counterfactual_endpoint(request)

@app.get("/api/counterfactual/{case_id}")
def counterfactual_get_endpoint(case_id: str):
    """Returns counterfactual analysis history for a specific case."""
    experiments = counterfactual_engine.get_case_experiments(case_id)
    return {
        "case_id": case_id,
        "experiments_count": len(experiments),
        "experiments": experiments
    }

# ============================================================
# PHASE 6: LITERATURE INTELLIGENCE & CLINICAL CASE REPORTING
# ============================================================

class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = Field(default=None)
    clinical_text: Optional[str] = Field(default=None)
    top_k: Optional[int] = Field(default=5)


@app.post("/api/literature/search")
def search_literature_endpoint(request: LiteratureSearchRequest):
    """
    Module 15: Searches PubMed via NCBI E-Utilities with targeted queries,
    scores semantic relevance, and classifies evidence categories.
    """
    if not request.disease_name or not request.disease_name.strip():
        raise HTTPException(status_code=400, detail="Disease name is required for literature search.")

    try:
        # Build queries
        queries = []
        if request.custom_query and request.custom_query.strip():
            queries.append(request.custom_query.strip())
        else:
            if request.genes:
                queries.append(PubMedQueryBuilder.build_disease_gene_query(request.disease_name, request.genes))
            if request.phenotypes:
                queries.append(PubMedQueryBuilder.build_phenotype_query(request.disease_name, request.phenotypes))
            queries.append(PubMedQueryBuilder.build_indian_cohort_query(request.disease_name))
            queries.append(PubMedQueryBuilder.build_disease_query(request.disease_name))

        all_pmids = []
        for q in queries:
            pmids = pubmed_client.search_pmids(q, max_results=request.max_results)
            for pid in pmids:
                if pid not in all_pmids:
                    all_pmids.append(pid)
            if len(all_pmids) >= request.max_results:
                break

        articles = pubmed_client.fetch_articles_by_pmids(all_pmids[:request.max_results])

        # Score relevance & classify evidence
        if articles:
            doc_texts = [f"{a.title} {a.abstract}" for a in articles]
            query_ctx = f"{request.disease_name} {' '.join(request.genes)} {' '.join(request.phenotypes)}"
            relevance_scores = relevance_scorer.compute_similarity(query_ctx, doc_texts)

            for art, score in zip(articles, relevance_scores):
                art.relevance_score = score
                EvidenceClassifier.classify_article(
                    article=art,
                    disease_name=request.disease_name,
                    patient_phenotypes=request.phenotypes,
                    genes=request.genes
                )

            # Sort articles by relevance
            articles.sort(key=lambda x: x.relevance_score, reverse=True)

        return {
            "disease_id": request.disease_id or "UNKNOWN",
            "disease_name": request.disease_name,
            "total_found": len(articles),
            "articles": [a.dict() for a in articles]
        }
    except Exception as e:
        logger.error(f"Literature search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Literature search error: {str(e)}")


@app.get("/api/literature/{pmid}")
def get_literature_article_endpoint(pmid: str):
    """Retrieves full metadata and abstract for a specific PubMed ID."""
    articles = pubmed_client.fetch_articles_by_pmids([pmid])
    if not articles:
        raise HTTPException(status_code=404, detail=f"PubMed article {pmid} not found.")
    return articles[0].dict()


@app.get("/api/evidence/profile/{disease_id}")
def get_evidence_profile_endpoint(disease_id: str, case_id: Optional[str] = None):
    """Module 15: Returns complete disease evidence profile (literature, categories, strength)."""
    case_context = case_store.get(case_id) if case_id else None
    
    # Locate candidate
    cand = None
    if case_context:
        for c in (case_context.get("fused_candidates") or case_context.get("ranked_candidates", [])):
            if c.get("disease_id") == disease_id:
                cand = c
                break

    disease_name = cand.get("disease_name") if cand else disease_id
    genes = cand.get("genes", []) if cand else []
    phenotypes = [p.get("text", "") if isinstance(p, dict) else str(p) for p in (case_context.get("extracted_phenotypes", []) if case_context else [])]

    # Search articles
    search_req = LiteratureSearchRequest(
        disease_id=disease_id,
        disease_name=disease_name,
        genes=genes,
        phenotypes=phenotypes,
        max_results=8
    )
    search_res = search_literature_endpoint(search_req)
    raw_articles = [PubMedArticle(**a) for a in search_res["articles"]]

    profile = DiseaseEvidenceProfileBuilder.build_profile(
        disease_id=disease_id,
        disease_name=disease_name,
        articles=raw_articles,
        patient_phenotypes=phenotypes
    )
    return profile.dict()


@app.get("/api/evidence/matrix/{disease_id}")
def get_evidence_matrix_endpoint(disease_id: str, case_id: Optional[str] = None):
    """Module 15: Returns Phenotype x Literature Evidence Matrix for a candidate disease."""
    case_context = case_store.get(case_id) if case_id else None
    
    cand = None
    if case_context:
        for c in (case_context.get("fused_candidates") or case_context.get("ranked_candidates", [])):
            if c.get("disease_id") == disease_id:
                cand = c
                break

    disease_name = cand.get("disease_name") if cand else disease_id
    genes = cand.get("genes", []) if cand else []
    
    # Format phenotypes
    phenotypes = []
    if case_context:
        for h in case_context.get("hpo_terms", []):
            phenotypes.append({"text": h.get("name", h.get("term", "")), "hpo_id": h.get("id", "")})
        if not phenotypes:
            phenotypes = case_context.get("extracted_phenotypes", [])

    if not phenotypes:
        phenotypes = ["hypotonia", "short stature", "developmental delay", "seizures"]

    search_req = LiteratureSearchRequest(
        disease_id=disease_id,
        disease_name=disease_name,
        genes=genes,
        phenotypes=[p.get("text", "") if isinstance(p, dict) else str(p) for p in phenotypes],
        max_results=6
    )
    search_res = search_literature_endpoint(search_req)
    raw_articles = [PubMedArticle(**a) for a in search_res["articles"]]

    matrix_res = EvidenceMatrixBuilder.build_matrix(
        disease_id=disease_id,
        disease_name=disease_name,
        phenotypes=phenotypes,
        articles=raw_articles
    )
    return matrix_res.dict()


@app.post("/api/report/generate", response_model=ClinicalCaseReport)
def generate_report_endpoint(request: ReportGenerateRequest):
    """
    Module 16: Synthesizes complete 11-section Clinical Case Report
    from active case context and literature intelligence.
    """
    case_context = None
    if request.case_id and request.case_id in case_store:
        case_context = case_store[request.case_id]
    elif case_store:
        # Pick most recent case
        latest_id = list(case_store.keys())[-1]
        case_context = case_store[latest_id]
    elif request.clinical_text:
        # Run diagnosis to produce case context
        diag_res = diagnose_endpoint(DiagnoseRequest(text=request.clinical_text, top_k=request.top_k or 5))
        case_context = case_store[diag_res["case_id"]]
    else:
        raise HTTPException(
            status_code=400,
            detail="No active case found. Please provide clinical_text or run diagnostic analysis first."
        )

    top_cands = case_context.get("fused_candidates") or case_context.get("ranked_candidates", [])
    top_cand = top_cands[0] if top_cands else None
    top_disease_name = top_cand.get("disease_name", "Rare Disease Candidate") if top_cand else "Candidate"
    top_disease_id = top_cand.get("disease_id", "OMIM:000000") if top_cand else "ID:0000"

    # Fetch literature summary for top candidate
    lit_summary = None
    try:
        profile_dict = get_evidence_profile_endpoint(disease_id=top_disease_id, case_id=case_context.get("case_id"))
        matrix_dict = get_evidence_matrix_endpoint(disease_id=top_disease_id, case_id=case_context.get("case_id"))
        lit_summary = {
            "total_articles": profile_dict.get("total_articles", 0),
            "top_articles": profile_dict.get("top_articles", []),
            "indian_cohort_articles": profile_dict.get("indian_cohort_articles", []),
            "matrix_preview": matrix_dict.get("matrix", [])
        }
    except Exception as e:
        logger.warning(f"Could not compile literature summary for report: {e}")

    report = CaseReportGenerator.generate_report(
        case_data=case_context,
        literature_summary=lit_summary
    )

    report_store[report.header.report_id] = report
    return report


@app.get("/api/report/{report_id}")
def get_report_endpoint(report_id: str):
    """Retrieves generated Clinical Case Report by report_id."""
    if report_id not in report_store:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")
    return report_store[report_id]


@app.get("/api/report/{report_id}/export")
def export_report_endpoint(report_id: str):
    """Renders and returns formatted print-ready HTML for the case report."""
    if report_id not in report_store:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")
    
    from fastapi.responses import HTMLResponse
    html_content = CaseReportGenerator.export_to_html(report_store[report_id])
    return HTMLResponse(content=html_content, status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)

