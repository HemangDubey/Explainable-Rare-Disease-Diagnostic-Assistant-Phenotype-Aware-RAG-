import os
import sys
import yaml
import uuid
import logging
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

sys.path.append(os.path.abspath("."))

from src.env_loader import load_env
load_env()

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
from src.counterfactual.scenario import run_scenario
from src.scribe.note_structurer import NoteStructurer
from src.scribe.draft_schema import Draft, DraftUpdate
from src.scribe.draft_store import DbDraftStore, DraftNotFound, PersistenceError
from src.api import repo
from src.api.auth_routes import router as auth_router, auth_gate, current_user
from src.api import genomic_routes, twin_routes
from src.auth.service import AuthUser, purge_sessions
from src.db import session as dbsession
from src.db.errors import StorageError
from src.db.migrate import schema_is_current, upgrade_head
from src.input_guard.input_validator import InputValidatorGuard
from src.input_guard.groq_provider import resolve_model
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

APP_ENV = os.environ.get("APP_ENV", "development").lower()
PRODUCTION = APP_ENV == "production"
app = FastAPI(
    title="Explainable Rare-Disease Diagnostic Assistant API",
    description="Phenotype-aware retrieval with grounded explanations, counterfactual lab and evidence intelligence. Authenticated, database-backed (Phase 7R).",
    version="7.0.0",
    dependencies=[Depends(auth_gate)],                     # every route except the public paths needs a valid session
    docs_url=None if PRODUCTION else "/docs", redoc_url=None if PRODUCTION else "/redoc", openapi_url=None if PRODUCTION else "/openapi.json",
)
app.include_router(auth_router)
app.include_router(twin_routes.router)
app.include_router(genomic_routes.router)

# Enable CORS for React Vite frontend (port 5173, etc.)
# ---- CORS: explicit allowlist (comma-separated CORS_ALLOW_ORIGINS); no wildcard, no credentials ----
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS = [o.strip() for o in (os.environ.get("CORS_ALLOW_ORIGINS") or _DEFAULT_ORIGINS).split(",") if o.strip() and o.strip() != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---- request-size limit and in-memory per-client rate limiting (single-process; use a gateway for multi-instance deployments) ----
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 262144))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", 300))
RATE_LIMIT_LLM_PER_MIN = int(os.environ.get("RATE_LIMIT_LLM_PER_MIN", 30))
_LLM_PATHS = ("/api/reason", "/api/explain", "/api/copilot", "/api/input/enhance", "/api/diagnose")
AUTH_RATE_LIMIT_PER_MIN = int(os.environ.get("AUTH_RATE_LIMIT_PER_MIN", 10))     # per client IP, process-local
_AUTH_PATHS = ("/api/auth/login", "/api/auth/register")
_hits: Dict[str, list] = {}


@app.middleware("http")
async def _guard(request: Request, call_next):
    if request.method != "OPTIONS":
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": {"status": "payload_too_large", "message": f"Request body exceeds {MAX_BODY_BYTES} bytes."}})
        import time as _t
        now = _t.time()
        client = request.client.host if request.client else "unknown"
        for bucket, limit in (("all", RATE_LIMIT_PER_MIN), ("llm", RATE_LIMIT_LLM_PER_MIN), ("auth", AUTH_RATE_LIMIT_PER_MIN)):
            if bucket == "llm" and request.url.path not in _LLM_PATHS:
                continue
            if bucket == "auth" and request.url.path not in _AUTH_PATHS:
                continue
            key = f"{bucket}:{client}"
            window = [t for t in _hits.get(key, []) if now - t < 60]
            if len(window) >= limit:
                _hits[key] = window
                return JSONResponse(status_code=429, headers={"Retry-After": "30"},
                                    content={"detail": {"status": "rate_limited", "message": "Too many requests; please retry shortly."}})
            window.append(now)
            _hits[key] = window
        if len(_hits) > 5000:
            _hits.clear()
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    if PRODUCTION:                                          # TLS is terminated by the platform / reverse proxy
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(StorageError)
async def _storage_unavailable(request: Request, exc: StorageError):
    return JSONResponse(status_code=503, content={"detail": {"status": "database_unavailable", "message": "The database is temporarily unavailable. Please retry."}})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.error("Unhandled %s on %s", type(exc).__name__, request.url.path)     # type and path only: no message, no body
    return JSONResponse(status_code=500, content={"detail": {"status": "internal_error", "message": "Unexpected server error."}})

# Global pipeline & reasoning instances
config = {}
retrieval_pipeline = None
ranking_pipeline = None
fusion_engine = None
llm_reasoner = None
differential_engine = None
doctor_copilot = None
scribe_engine = None
note_structurer = None
draft_store = DbDraftStore()
db_state = {"status": "uninitialised"}
counterfactual_engine = None
input_guard = None

# Phase 6 singletons
pubmed_client = None
relevance_scorer = None

# In-memory case context session store for persistent navigation
retrieval_error: Dict[str, str] = {}


def _require_pipeline():
    if ranking_pipeline is None or retrieval_pipeline is None:
        raise HTTPException(status_code=503, detail="Retrieval pipeline unavailable (real embedding model/index not loaded). " + retrieval_error.get("message", ""))


def _case(case_id, user):
    """Owner-scoped lookup: returns the case only if it belongs to `user`; unknown ids and other users' ids are both None."""
    return repo.get_case(user.id, case_id) if case_id else None


def _init_database():
    """Validate configuration, then migrate/verify the schema. Never raises in development (the app starts degraded and protected
    routes answer 503); in production an invalid configuration refuses to start."""
    problems = []
    if PRODUCTION:
        if not os.environ.get("DATABASE_URL"):
            problems.append("DATABASE_URL must be set in production")
        elif dbsession.is_sqlite():
            logger.warning("production is using SQLite; PostgreSQL is recommended for multi-user deployments")
        if not os.environ.get("CORS_ALLOW_ORIGINS"):
            problems.append("CORS_ALLOW_ORIGINS must list the trusted frontend origin(s) in production")
        if any("localhost" in o or "127.0.0.1" in o for o in CORS_ORIGINS):
            problems.append("CORS_ALLOW_ORIGINS must not contain localhost origins in production")
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    try:
        if os.environ.get("AUTO_MIGRATE", "0" if PRODUCTION else "1").lower() in ("1", "true", "yes"):
            upgrade_head()
        db_state["status"] = "ok" if schema_is_current() else "schema_outdated"
    except Exception as e:  # noqa: BLE001
        logger.error("database initialisation failed: %s", type(e).__name__)
        db_state["status"] = "unavailable"
    retention = int(os.environ.get("RETENTION_DAYS", 0) or 0)
    if retention > 0 and db_state["status"] == "ok":
        import threading
        import time as _time

        def _purge_loop():
            while True:
                try:
                    out = repo.purge_older_than(retention)
                    purge_sessions()
                    logger.info("retention purge (%d days): %s", retention, out)
                except Exception as e:  # noqa: BLE001
                    logger.error("retention purge failed: %s", type(e).__name__)
                _time.sleep(6 * 3600)
        threading.Thread(target=_purge_loop, daemon=True, name="retention-purge").start()


@app.on_event("startup")
def startup_event():
    _init_database()
    global note_structurer, config, retrieval_pipeline, ranking_pipeline, fusion_engine, llm_reasoner, differential_engine, doctor_copilot, scribe_engine, counterfactual_engine, input_guard, pubmed_client, relevance_scorer
    config_path = "configs/config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("Initializing NER -> HPO -> real-embedding retrieval pipeline...")
    try:
        retrieval_pipeline = Phase2RetrievalPipeline(model_key="primary", config_path=config_path)
        ranking_pipeline = Phase3RankingPipeline(model_key="primary", config_path=config_path, retrieval_pipeline=retrieval_pipeline)
    except Exception as e:  # real models/indexes unavailable: report loudly, never fall back to fake vectors
        retrieval_pipeline = ranking_pipeline = None
        retrieval_error["message"] = f"{type(e).__name__}: {e}"
        logger.error("Retrieval pipeline unavailable: %s", retrieval_error["message"])

    logger.info("Initializing Phase 4 Reasoning & Evidence Engines...")
    fusion_engine = EvidenceFusionEngine(config=config)
    llm_reasoner = LLMReasoner(config=config)
    differential_engine = DifferentialEngine(config=config)
    doctor_copilot = DoctorCopilot(config=config)
    if retrieval_pipeline is not None:
        from src.ranking.disease_ranker import load_ranking_config
        fusion_engine.set_context({r["disease_id"]: r for r in retrieval_pipeline.retriever.store.disease_records},
                                  load_ranking_config(config_path))

    if retrieval_pipeline is not None:                 # Phase 7R.5 Digital Twin: ontology for region mapping + gene-level evidence
        _lk = ranking_pipeline.disease_ranker.pop.lookup
        twin_routes.configure(hpo_terms=retrieval_pipeline.normalizer.res.terms,
                              gene_record=lambda sym: (_lk.genes.get(str(sym).upper()) or {}).get("rec"),
                              gene_lookup=_lk.lookup_gene, indigen_available=lambda: _lk.indigen.available)
        try:                                           # one gene-evidence service for the twin and /api/genomic
            from src.population.gene_evidence import GeneEvidenceService
            _genes = GeneEvidenceService(_lk)
            twin_routes.configure_gene_service(_genes)
            genomic_routes.configure(_genes)
        except Exception as e:  # noqa: BLE001 - the rest of the API keeps working; genomic routes report 503
            logger.error("Gene evidence service unavailable: %s", type(e).__name__)

    logger.info("Initializing Phase 5 Scribe & Counterfactual Engines...")
    if ranking_pipeline is not None:
        scribe_engine = ClinicalScribeEngine(config_path=config_path)
        counterfactual_engine = CounterfactualEngine(ranking_pipeline=ranking_pipeline, config_path=config_path)
        note_structurer = NoteStructurer(extractor=_note_extractor)

    logger.info("Initializing Input Quality Gate & AI Enhancement Guard...")
    groq_cfg = config.get("groq", {})
    input_guard = InputValidatorGuard(
        groq_api_key=groq_cfg.get("api_key"),
        groq_model=resolve_model(config)
    )

    logger.info("Initializing Phase 6 Literature Intelligence Engines...")
    pubmed_client = PubMedClient()
    relevance_scorer = LiteratureRelevanceScorer()

    logger.info("All Phase 1-6 pipelines, reasoning & evidence intelligence engines initialized successfully.")

def _fuse(p3_res, clinical_text, top_k):
    """Single place where ranked candidates become evidence packets (used by every reasoning route)."""
    return fusion_engine.fuse_all_candidates(
        p3_res["ranked_candidates"], p3_res["phenotypes"], p3_res["hpo_terms"], top_k=top_k,
        clinical_text=clinical_text, retrieval_metadata=p3_res.get("retrieval_metadata"))


def _not_requested():
    return {"provider": {"name": "llm", "model": getattr(llm_reasoner.provider, "model", None), "status": "not_requested",
                         "fallback": False, "reason": "explanation not requested; call /api/reason or pass explain=true"},
            "candidates": []}



def _note_extractor(statement_text):
    """Existing Phase 1/2R NER + HPO normalisation, applied to one statement (no second pipeline)."""
    if retrieval_pipeline is None:
        raise RuntimeError("retrieval pipeline unavailable")
    phenos, mappings, _, _ = retrieval_pipeline.extract_and_map(statement_text)
    out = []
    for p, m in zip(phenos, mappings):
        if p["mapping_status"] == "non_phenotype" and len(p["mention"].split()) > 1:
            # NER sometimes returns '<modifier> <phenotype>' (e.g. 'recurrent seizures'); try the same words without the leading modifier
            rest = p["mention"].split(None, 1)[1]
            r2 = retrieval_pipeline.normalizer.normalize_detailed(rest)
            if r2["status"] in ("exact", "synonym", "lexical", "semantic") and r2.get("is_phenotypic", True):
                p = {**p, "hpo_id": r2["hpo_id"], "hpo_term": r2["term"], "mapping_status": r2["status"] + "_after_modifier_strip", "mapping_score": r2["score"]}
        out.append({"mention": p["mention"], "start": p["start"], "end": p["end"], "hpo_id": p.get("hpo_id") if p["mapping_status"] != "non_phenotype" else None,
                    "hpo_term": p.get("hpo_term") if p["mapping_status"] != "non_phenotype" else None, "mapping_status": p["mapping_status"],
                    "mapping_score": p.get("mapping_score"), "candidates": m.get("candidates") or m.get("suggestions") or []})
    return out


def _evidence_for_terms(ranked, hpo_terms, top_k):
    """Phase 4R fusion for a (possibly hypothetical) HPO set; no text, so no negation inference."""
    phen = [{"mention": h["name"], "start": 0, "end": 0, "hpo_id": h["hpo_id"], "mapping_status": h.get("status") or "exact"} for h in hpo_terms]
    return fusion_engine.fuse_all_candidates(ranked, phen, hpo_terms, top_k=top_k, clinical_text="", retrieval_metadata=None)

# Request / Response Schemas
class _TextInput(BaseModel):
    """`clinical_text` is canonical; `text` is accepted for backward compatibility."""
    clinical_text: Optional[str] = Field(default=None, example="Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.")
    text: Optional[str] = Field(default=None)

    def get_text(self) -> str:
        return (self.clinical_text if self.clinical_text is not None else self.text) or ""


class ClinicalTextRequest(_TextInput):
    top_k: Optional[int] = Field(default=10, example=10)
    strategy: Optional[str] = Field(default=None, example="mean_vector")

class RankRequest(_TextInput):
    top_k: Optional[int] = Field(default=10, example=10)
    exp_config: Optional[str] = Field(default="rag_south_asian_global", example="rag_south_asian_global")

class DiagnoseRequest(_TextInput):
    top_k: Optional[int] = Field(default=5, example=5)
    explain: Optional[bool] = Field(default=False, description="also run the grounded language-model explanation (slower); otherwise use /api/reason")
    exp_config: Optional[str] = Field(default="rag_south_asian_global", example="rag_south_asian_global")
    case_id: Optional[str] = Field(default=None, example=None)

class ReasonRequest(BaseModel):
    case_id: Optional[str] = Field(default=None)
    clinical_text: Optional[str] = Field(default=None)
    top_k: Optional[int] = Field(default=5)


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
        "version": "7.0.0",
        "status": "healthy" if ranking_pipeline is not None else "degraded",
        "retrieval": (retrieval_pipeline.retriever.info if retrieval_pipeline else {"available": False, "error": retrieval_error.get("message")}),
        "llm": provider_health,
        "database": {"status": db_state["status"] if dbsession.ping() else "unavailable"},
    }

@app.post("/api/retrieve")
def retrieve_endpoint(request: ClinicalTextRequest):
    """BiomedBERT NER -> HPO normalisation -> real S-PubMedBERT embeddings -> FAISS -> candidate diseases."""
    _require_pipeline()
    text = request.get_text()
    if not text.strip():
        raise HTTPException(status_code=400, detail="clinical_text must not be empty.")
    try:
        r = retrieval_pipeline.run(text, top_k_disease=request.top_k or 10, strategy=request.strategy)
        return {
            "clinical_text": text,
            "extracted_phenotypes": r["phenotypes"],
            "hpo_mappings": r["hpo_mappings"],
            "unmatched_phenotypes": r["unmatched_phenotypes"],
            "candidates": r["candidate_diseases"],
            "retrieval_metadata": r["retrieval_metadata"],
        }
    except Exception as e:
        logger.error(f"Retrieval error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail={"status": "pipeline_error", "message": f"Retrieval error ({type(e).__name__})."})

@app.post("/api/rank")
def rank_endpoint(request: RankRequest):
    _require_pipeline()
    text = request.get_text()
    if not text.strip():
        raise HTTPException(status_code=400, detail="clinical_text must not be empty.")
    try:
        results = ranking_pipeline.run(clinical_text=text, top_k_disease=request.top_k or 10,
                                       exp_config=request.exp_config or "rag_south_asian_global")
        return {
            "phenotypes": results["phenotypes"],
            "hpo_mappings": results["hpo_mappings"],
            "hpo_terms": results["hpo_terms"],
            "unmatched_phenotypes": results["unmatched_phenotypes"],
            "retrieved_candidates": results["retrieved_candidates"],
            "ranked_candidates": results["ranked_candidates"],
            "ranking_explanations": results["ranking_explanations"],
            "retrieval_metadata": results["retrieval_metadata"],
            "population_coverage": results["population_coverage"],
        }
    except Exception as e:
        logger.error(f"Ranking error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail={"status": "pipeline_error", "message": f"Ranking error ({type(e).__name__})."})

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
def diagnose_endpoint(request: DiagnoseRequest, user: AuthUser = Depends(current_user)):
    """
    End-to-End Diagnostic Pipeline (Phases 1 → 2 → 3 → 4):
    Clinical Text -> BiomedBERT NER -> HPO Normalization -> FAISS Retrieval ->
    IndiGen / gnomAD Re-ranking -> Evidence Fusion -> LLM Clinical Reasoning -> Differential Analysis.
    """
    _require_pipeline()
    clinical_text = request.get_text()
    if not clinical_text.strip():
        raise HTTPException(status_code=400, detail="Clinical case text must not be empty.")

    # Quality Gate Check
    if input_guard:
        val_res = input_guard.validate_input(clinical_text)
        if not val_res.is_valid_clinical:
            raise HTTPException(status_code=400, detail=val_res.reason)

    try:
        case_id = request.case_id or str(uuid.uuid4())[:8]

        # 1. Execute Phase 3 Ranking Pipeline (contains Phase 1 NER, Phase 2 FAISS, Phase 3 Priors)
        p3_results = ranking_pipeline.run(
            clinical_text=clinical_text,
            top_k_disease=request.top_k or 5,
            exp_config=request.exp_config or "rag_south_asian_global"
        )

        extracted_phenotypes = p3_results.get("phenotypes", [])
        hpo_mappings = p3_results.get("hpo_mappings", [])
        unmatched = p3_results.get("unmatched_phenotypes", [])
        retrieval_metadata = p3_results.get("retrieval_metadata", {})
        population_coverage = p3_results.get("population_coverage", {})
        hpo_terms = p3_results.get("hpo_terms", [])
        ranked_candidates = p3_results.get("ranked_candidates", [])

        # 2. Phase 4 Evidence Fusion
        fused_candidates = _fuse(p3_results, clinical_text, request.top_k or 5)

        # 3. Grounded explanation (language model) - only when requested; otherwise status "not_requested" (never a fake result)
        reasoning = (llm_reasoner.explain_candidates(clinical_text, [c["packet"] for c in fused_candidates])
                     if request.explain else _not_requested())
        top_explanation = reasoning["candidates"][0] if reasoning["candidates"] else None

        # 4. Phase 4 Differential Diagnosis Synthesis
        differential = differential_engine.generate_differential(
            fused_candidates=fused_candidates,
            clinical_case_text=clinical_text
        )

        # Store in case context session store
        case_context = {
            "case_id": case_id,
            "clinical_text": clinical_text,
            "extracted_phenotypes": extracted_phenotypes,
            "hpo_terms": hpo_terms,
            "hpo_mappings": hpo_mappings,
            "unmatched_phenotypes": unmatched,
            "retrieval_metadata": retrieval_metadata,
            "ranked_candidates": ranked_candidates,
            "fused_candidates": fused_candidates,
            "top_explanation": top_explanation,
            "reasoning": reasoning,
            "differential": differential
        }
        case_id = repo.save_case(user.id, case_id, case_context)

        return {
            "case_id": case_id,
            "clinical_text": clinical_text,
            "extracted_phenotypes": extracted_phenotypes,
            "hpo_terms": hpo_terms,
            "hpo_mappings": hpo_mappings,
            "unmatched_phenotypes": unmatched,
            "retrieval_metadata": retrieval_metadata,
            "population_coverage": population_coverage,
            "fused_candidates": fused_candidates,
            "top_explanation": top_explanation,
            "reasoning": reasoning,
            "llm": llm_reasoner.provider.check_health(),
            "differential": differential,
            "disclaimer": "Research decision-support prototype. Prioritized candidates are NOT diagnoses; scores are not probabilities; absence of evidence in this system does not establish absence of disease. Interpretation by qualified clinicians and genetic confirmation are required."
        }
    except StorageError:
        raise                                    # becomes HTTP 503 database_unavailable
    except Exception as e:
        logger.error(f"Diagnose pipeline error: {type(e).__name__}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "pipeline_error", "message": f"Diagnostic pipeline error ({type(e).__name__})."})

@app.post("/api/reason")
def reason_endpoint(request: ReasonRequest, user: AuthUser = Depends(current_user)):
    """Grounded language-model explanation for ALL top candidates of an analysed case (one structured request)."""
    _require_pipeline()
    case = _case(request.case_id, user) if request.case_id else None
    if case is None:
        if not (request.clinical_text and request.clinical_text.strip()):
            raise HTTPException(status_code=400, detail="Either a valid case_id or clinical_text must be provided.")
        p3 = ranking_pipeline.run(request.clinical_text, top_k_disease=request.top_k or 5)
        case = {"clinical_text": request.clinical_text, "fused_candidates": _fuse(p3, request.clinical_text, request.top_k or 5)}
    packets = [c["packet"] for c in case["fused_candidates"][: request.top_k or 5]]
    reasoning = llm_reasoner.explain_candidates(case.get("clinical_text", ""), packets)
    case["reasoning"] = reasoning
    if request.case_id and _case(request.case_id, user) is not None:
        repo.save_case(user.id, request.case_id, case)          # the owner's case; stored so the explanation survives a restart
    return {"case_id": request.case_id, "reasoning": reasoning, "llm": llm_reasoner.provider.check_health()}


@app.post("/api/explain")
def explain_endpoint(request: ExplainRequest, user: AuthUser = Depends(current_user)):
    """
    Generates an evidence-grounded LLM explanation for any specific candidate disease.
    """
    case_context = _case(request.case_id, user) if request.case_id else None
    
    if not case_context:
        # If no case_id in store, run on-the-fly ranking
        if not request.clinical_text:
            raise HTTPException(status_code=400, detail="Either a valid case_id or clinical_text must be provided.")
        p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=5)
        fused = _fuse(p3_res, request.clinical_text, 5)
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
def differential_endpoint(request: DifferentialRequest, user: AuthUser = Depends(current_user)):
    """
    Compares prioritized candidate diseases side-by-side.
    """
    case_context = _case(request.case_id, user) if request.case_id else None
    if not case_context:
        if not request.clinical_text:
            raise HTTPException(status_code=400, detail="Either a valid case_id or clinical_text must be provided.")
        p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=request.top_k or 5)
        fused = _fuse(p3_res, request.clinical_text, request.top_k or 5)
        diff = differential_engine.generate_differential(fused, request.clinical_text)
        return diff

    return case_context.get("differential", {})

@app.post("/api/copilot")
def copilot_endpoint(request: CopilotRequest, user: AuthUser = Depends(current_user)):
    """
    Interactive Q&A with the Explainable AI Doctor Copilot for the current case.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    case_context = _case(request.case_id, user) if request.case_id else None
    if not case_context:
        if request.clinical_text and request.clinical_text.strip():
            p3_res = ranking_pipeline.run(request.clinical_text, top_k_disease=5)
            fused = _fuse(p3_res, request.clinical_text, 5)
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
def scribe_endpoint(request: ScribeRequest, user: AuthUser = Depends(current_user)):
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
        scribe_res.case_id = repo.save_case(user.id, scribe_res.case_id, {
            "case_id": scribe_res.case_id,
            "clinical_text": request.clinical_text,
            "structured_case": scribe_res.structured_case.dict(),
            "extracted_phenotypes": scribe_res.phenotypes,
            "hpo_terms": scribe_res.hpo_terms
        })
        scribe_res.structured_case.case_id = scribe_res.case_id

        return scribe_res
    except Exception as e:
        logger.error(f"Scribe extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "scribe_error", "message": f"Clinical Scribe error ({type(e).__name__})."})

@app.post("/api/counterfactual", response_model=CounterfactualResponse)
def counterfactual_endpoint(request: CounterfactualRequest, user: AuthUser = Depends(current_user)):
    """
    Phase 5 Counterfactual Diagnosis Lab:
    Executes controlled what-if analysis on candidate disease prioritization
    by adding, removing, or toggling phenotypes against the baseline pipeline.
    """
    try:
        own = _case(request.case_id, user) if request.case_id else None
        cf_res = counterfactual_engine.run_analysis(
            request=request,
            case_store={request.case_id: own} if own else {}      # only the caller's own case is visible to the engine
        )
        return cf_res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Counterfactual analysis error: {type(e).__name__}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "counterfactual_error", "message": f"Counterfactual analysis error ({type(e).__name__})."})

@app.post("/api/counterfactual/add", response_model=CounterfactualResponse)
def counterfactual_add_endpoint(request: CounterfactualRequest, user: AuthUser = Depends(current_user)):
    """Shortcut endpoint to add phenotypes in counterfactual analysis."""
    request.operation = "add"
    return counterfactual_endpoint(request, user)

@app.post("/api/counterfactual/remove", response_model=CounterfactualResponse)
def counterfactual_remove_endpoint(request: CounterfactualRequest, user: AuthUser = Depends(current_user)):
    """Shortcut endpoint to remove phenotypes in counterfactual analysis."""
    request.operation = "remove"
    return counterfactual_endpoint(request, user)

@app.post("/api/counterfactual/compare", response_model=CounterfactualResponse)
def counterfactual_compare_endpoint(request: CounterfactualRequest, user: AuthUser = Depends(current_user)):
    """Shortcut endpoint to compare two case states in counterfactual analysis."""
    request.operation = "compare"
    return counterfactual_endpoint(request, user)

@app.get("/api/counterfactual/{case_id}")
def counterfactual_get_endpoint(case_id: str, user: AuthUser = Depends(current_user)):
    """Returns counterfactual analysis history for a specific case."""
    if _case(case_id, user) is None:
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Case not found."})
    experiments = counterfactual_engine.get_case_experiments(case_id)
    return {
        "case_id": case_id,
        "experiments_count": len(experiments),
        "experiments": experiments
    }


# ============================================================
# PHASE 5R: CLINICAL SCRIBE DRAFTS + COUNTERFACTUAL SCENARIOS
# ============================================================

class ScribeDraftRequest(BaseModel):
    clinical_text: str = Field(..., description="Clinician note (this patient only)")
    supplied_phenotypes: Optional[List[str]] = Field(default=None, description="Optional clinician-entered phenotype list")
    check_enhancement: Optional[bool] = Field(default=False, description="also return the existing input-enhancement suggestion (never applied automatically)")
    save: Optional[bool] = Field(default=True)


def _err(status_code, status, message):
    return HTTPException(status_code=status_code, detail={"status": status, "message": message})


@app.post("/api/scribe/draft")
def scribe_draft_endpoint(request: ScribeDraftRequest, user: AuthUser = Depends(current_user)):
    """Structured, clinician-reviewable draft. Facts are verbatim spans of the input; missing items are 'not_provided'."""
    if note_structurer is None:
        raise _err(503, "provider_unavailable", "Scribe pipeline is not initialised.")
    text = request.clinical_text or ""
    if not text.strip():
        raise _err(422, "invalid_input", "clinical_text must not be empty.")
    if len(text) > 20000:
        raise _err(422, "invalid_input", "clinical_text is too long (limit 20000 characters).")
    check = input_guard.validate_input(text) if input_guard else None   # deterministic gate first (existing flow)
    if check is not None and not check.is_valid_clinical and check.status in ("NON_CLINICAL", "INAPPROPRIATE"):
        raise _err(422, "invalid_input", f"Input rejected by the quality gate: {check.status}.")
    status_info = {"quality_gate": check.status if check else "unavailable", "enhancement": "not_requested"}
    if request.check_enhancement and input_guard:
        enh = input_guard.enhance_text(text)       # existing backend-only utility; provider name is not exposed
        status_info["enhancement"] = {"status": enh.status, "suggestion": enh.enhanced_text if enh.status == "NEEDS_ENHANCEMENT" else None,
                                      "added_facts": enh.added_facts, "applied": False}
    try:
        draft = note_structurer.structure(text, supplied_phenotypes=request.supplied_phenotypes, input_status=status_info)
    except Exception as e:
        logger.error("Scribe draft failure: %s", type(e).__name__)
        raise _err(500, "validation_failure", f"Draft generation failed ({type(e).__name__}).")
    if request.save:
        try:
            draft = draft_store.create(draft, user.id)
        except PersistenceError:
            out = draft.model_dump()
            out.update(saved=False, persistence={"status": "persistence_failure", "message": "Draft could not be saved; it exists only in this response."})
            return out
    out = draft.model_dump()
    return out


@app.get("/api/scribe/draft/{draft_id}")
def scribe_draft_get(draft_id: str, user: AuthUser = Depends(current_user)):
    try:
        return draft_store.get(draft_id, user.id).model_dump()
    except DraftNotFound:
        raise _err(404, "not_found", "Draft not found.")
    except PersistenceError:
        raise _err(503, "persistence_failure", "Draft could not be read.")


@app.put("/api/scribe/draft/{draft_id}")
def scribe_draft_put(draft_id: str, update: DraftUpdate, user: AuthUser = Depends(current_user)):
    try:
        return draft_store.update(draft_id, user.id, update).model_dump()
    except DraftNotFound:
        raise _err(404, "not_found", "Draft not found.")
    except PersistenceError:
        raise _err(503, "persistence_failure", "Draft could not be saved; your edits were not persisted.")


@app.delete("/api/scribe/draft/{draft_id}")
def scribe_draft_delete(draft_id: str, user: AuthUser = Depends(current_user)):
    """Permanently deletes one of the caller's saved drafts."""
    try:
        draft_store.delete(draft_id, user.id)
        return {"status": "deleted", "draft_id": draft_id}
    except DraftNotFound:
        raise _err(404, "not_found", "Draft not found.")
    except PersistenceError:
        raise _err(503, "persistence_failure", "Draft could not be deleted.")


@app.delete("/api/case/{case_id}")
def delete_case(case_id: str, user: AuthUser = Depends(current_user)):
    """Deletes one of the caller's cases and everything derived from it (scenarios, reports)."""
    if not repo.delete_case(user.id, case_id):
        raise _err(404, "not_found", "Case not found.")
    return {"status": "deleted", "case_id": case_id}


@app.get("/api/cases")
def list_my_cases(user: AuthUser = Depends(current_user)):
    return {"cases": repo.list_cases(user.id)}


class ScenarioOperation(BaseModel):
    op: str = Field(..., description="add | remove | modify")
    phenotype: str = Field(..., description="HPO id or phenotype text (for modify: the existing term to replace)")
    replacement: Optional[str] = Field(default=None, description="modify only: replacement HPO id or text")


class ScenarioRequest(BaseModel):
    case_id: Optional[str] = None
    clinical_text: Optional[str] = None
    operations: List[ScenarioOperation] = Field(default_factory=list)
    top_k: Optional[int] = Field(default=5)
    exp_config: Optional[str] = Field(default="rag_south_asian_global")


@app.post("/api/counterfactual/scenario")
def counterfactual_scenario_endpoint(request: ScenarioRequest, user: AuthUser = Depends(current_user)):
    """Apply operations to a COPY of the case's phenotype set and re-run the real retrieval + ranking pipeline.
    Every scenario belongs to a case and to the authenticated owner; a text-only request first creates the owner's baseline case."""
    _require_pipeline()
    top_k = max(1, min(request.top_k or 5, 10))
    case = _case(request.case_id, user) if request.case_id else None
    case_id = request.case_id if case else None
    if case and case.get("hpo_terms"):
        baseline = case["hpo_terms"]
    elif request.case_id and not (request.clinical_text and request.clinical_text.strip()):
        raise _err(404, "not_found", "Case not found.")
    elif request.clinical_text and request.clinical_text.strip():
        try:
            phenos, _m, baseline, _u = retrieval_pipeline.extract_and_map(request.clinical_text)
        except Exception as e:
            raise _err(500, "validation_failure", f"Could not extract phenotypes ({type(e).__name__}).")
        if baseline:
            case_id = repo.save_case(user.id, None, {"clinical_text": request.clinical_text, "extracted_phenotypes": phenos, "hpo_terms": baseline,
                                                     "origin": "counterfactual_baseline"})
    else:
        raise _err(422, "invalid_input", "Provide a known case_id or clinical_text.")
    if not baseline:
        raise _err(422, "unresolved_phenotype", "No phenotype could be mapped to an HPO term for the baseline case.")
    bad = [o.op for o in request.operations if o.op.lower() not in ("add", "remove", "modify")]
    if bad:
        raise _err(422, "invalid_input", f"Unsupported operation(s): {bad}. Use add, remove or modify.")
    ops = [{"op": o.op, "phenotype": o.phenotype, "replacement": o.replacement} for o in request.operations]
    try:
        res = run_scenario(ranking_pipeline, counterfactual_engine.normalizer, baseline, ops, top_k=top_k,
                           exp_config=request.exp_config or "rag_south_asian_global", evidence_fn=_evidence_for_terms)
    except Exception as e:
        logger.error("Scenario failure: %s", type(e).__name__, exc_info=True)
        raise _err(500, "validation_failure", f"Scenario could not be computed ({type(e).__name__}).")
    res["case_id"] = case_id
    if not repo.save_scenario(user.id, case_id, ops, res):
        raise _err(404, "not_found", "Case not found.")
    return res


@app.get("/api/counterfactual/scenario/{scenario_id}")
def counterfactual_scenario_get(scenario_id: str, user: AuthUser = Depends(current_user)):
    res = repo.get_scenario(user.id, scenario_id)
    if res is None:
        raise _err(404, "not_found", "Scenario not found.")
    return res

# ============================================================
# PHASE 6: LITERATURE INTELLIGENCE & CLINICAL CASE REPORTING
# ============================================================

class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = Field(default=None)
    clinical_text: Optional[str] = Field(default=None)
    top_k: Optional[int] = Field(default=5)
    include_indigen_demo: bool = Field(default=False, description="append a clearly labelled SYNTHETIC IndiGen demo appendix (not evidence)")


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
        raise HTTPException(status_code=500, detail={"status": "literature_error", "message": f"Literature search error ({type(e).__name__})."})


@app.get("/api/literature/{pmid}")
def get_literature_article_endpoint(pmid: str):
    """Retrieves full metadata and abstract for a specific PubMed ID."""
    articles = pubmed_client.fetch_articles_by_pmids([pmid])
    if not articles:
        raise HTTPException(status_code=404, detail=f"PubMed article {pmid} not found.")
    return articles[0].dict()


@app.get("/api/evidence/profile/{disease_id}")
def get_evidence_profile_endpoint(disease_id: str, case_id: Optional[str] = None, user: AuthUser = Depends(current_user)):
    """Module 15: Returns complete disease evidence profile (literature, categories, strength)."""
    case_context = _case(case_id, user) if case_id else None
    
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
def get_evidence_matrix_endpoint(disease_id: str, case_id: Optional[str] = None, user: AuthUser = Depends(current_user)):
    """Module 15: Returns Phenotype x Literature Evidence Matrix for a candidate disease."""
    case_context = _case(case_id, user) if case_id else None
    
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
def generate_report_endpoint(request: ReportGenerateRequest, user: AuthUser = Depends(current_user)):
    """
    Module 16: Synthesizes complete 11-section Clinical Case Report
    from active case context and literature intelligence.
    """
    case_context, report_case_id = None, None
    owned = _case(request.case_id, user) if request.case_id else None
    if owned is not None:
        case_context, report_case_id = owned, request.case_id
    elif request.clinical_text:
        # Run diagnosis to produce the OWNER's case context (never another user's most recent case)
        diag_res = diagnose_endpoint(DiagnoseRequest(clinical_text=request.clinical_text, top_k=request.top_k or 5), user)
        report_case_id = diag_res["case_id"]
        case_context = _case(report_case_id, user)
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
        profile_dict = get_evidence_profile_endpoint(disease_id=top_disease_id, case_id=case_context.get("case_id"), user=user)
        matrix_dict = get_evidence_matrix_endpoint(disease_id=top_disease_id, case_id=case_context.get("case_id"), user=user)
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
        literature_summary=lit_summary,
        indigen_demo_appendix=_indigen_demo_appendix(top_cands) if request.include_indigen_demo else None,
    )

    new_id = repo.save_report(user.id, report_case_id, report.model_dump())
    if new_id is None:
        raise _err(404, "not_found", "Case not found.")
    report.header.report_id = new_id
    return report


def _indigen_demo_appendix(cands) -> Optional[Dict[str, Any]]:
    """Synthetic IndiGen demo appendix for a report (opt-in). Built from the demo provider only; nothing in the report's evidence sections
    changes. Returns a 'disabled' / 'superseded' stub instead of values when the demo must not be shown."""
    from src.population.indigen_demo import DEMO_LABEL, demo_allowed
    svc = genomic_routes._ctx.get("service")
    if svc is None:
        return None
    base = {"label": DEMO_LABEL, "synthetic": True,
            "note": "Shown for demonstration only. Not used for ranking, scoring, or any conclusion in this report."}
    if svc.lookup.indigen.available:
        return {**base, "status": "superseded_by_real_data", "genes": []}
    if not demo_allowed():
        return {**base, "status": "disabled", "genes": []}
    genes = []
    for c in (cands or [])[:5]:
        for g in c.get("genes") or c.get("associated_genes") or []:
            if g not in [x["gene"] for x in genes]:
                d = svc.demo.gene(g)
                genes.append({"gene": g, "status": d.get("status"), "demo_caf": d.get("cumulative_af"), "n_variants": d.get("n_variants")})
    prov = svc.demo.provenance if svc.demo.available else {}
    return {**base, "status": "available" if svc.demo.available else "unavailable", "statement": prov.get("statement"),
            "generator": prov.get("generator"), "seed": prov.get("seed"), "genes": genes[:12]}


@app.get("/api/report/{report_id}")
def get_report_endpoint(report_id: str, user: AuthUser = Depends(current_user)):
    """Retrieves one of the caller's generated Clinical Case Reports."""
    data = repo.get_report(user.id, report_id)
    if data is None:
        raise _err(404, "not_found", "Report not found.")
    return data


@app.get("/api/report/{report_id}/export")
def export_report_endpoint(report_id: str, user: AuthUser = Depends(current_user)):
    """Renders print-ready HTML (all dynamic values escaped) for one of the caller's reports."""
    data = repo.get_report(user.id, report_id)
    if data is None:
        raise _err(404, "not_found", "Report not found.")
    from fastapi.responses import HTMLResponse
    repo.record_export(user.id, report_id)
    return HTMLResponse(content=CaseReportGenerator.export_to_html(ClinicalCaseReport(**data)), status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)

