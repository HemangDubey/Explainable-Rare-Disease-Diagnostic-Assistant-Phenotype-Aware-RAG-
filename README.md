<p align="center">
  <img src="https://lh3.googleusercontent.com/aida/AEtjO1WsvG4PmtCG5os6CRAflm_m7FddHjQ1303ktfydHJYjv73FM4gZdW8u-WsJuxbsBABuo5yixcrlsh4usHyJ1WM1hKOJ6Zb9GkurAKXxLYdnXVVhjoRkgWmx8A9C6MGG4mS3TN3aahW9_WiX8r03km6-YLg3AMyJ1gU0k-Xbi8sKH6RceS4hSiPgJN6baSnx3yGLjB7_Mxx9cDA8TAO1ltc5C60hM9RUr_z2u-6KCczeC4ccZYNNsweV_g" width="120" alt="ERDDA Logo">
</p>

<h1 align="center">Explainable Rare-Disease Diagnostic Assistant</h1>
<h3 align="center">Phenotype-Aware RAG with Population-Frequency Evidence (gnomAD global &amp; South Asian)</h3>

<p align="center">
  <a href="#architecture"><img src="https://img.shields.io/badge/Pipeline-6_Phases-006874?style=for-the-badge" alt="6 Phase Pipeline"></a>
  <a href="#phase-1-biomedical-ner"><img src="https://img.shields.io/badge/NER_F1-0.7203-0a2540?style=for-the-badge" alt="NER F1"></a>
  <a href="#phase-2-knowledge-rag"><img src="https://img.shields.io/badge/HPO_Terms-20%2C482-006874?style=for-the-badge" alt="HPO Terms"></a>
  <a href="#phase-3-population-priors"><img src="https://img.shields.io/badge/Population-gnomAD_Global_%2B_South_Asian-99f0fe?style=for-the-badge&labelColor=0a2540" alt="Population Aware"></a>
  <a href="#phase-6-evidence--literature-intelligence--clinical-case-report-generation"><img src="https://img.shields.io/badge/PubMed-NCBI_Integrated-006874?style=for-the-badge" alt="PubMed Integrated"></a>
</p>

<p align="center">
  An evidence-driven diagnostic assistant that extracts clinical phenotypes from unstructured text, retrieves rare-disease knowledge via semantic search, reports population-frequency evidence (ClinVar × gnomAD v4.1, global and South Asian reported separately; IndiGen not available), performs explainable counterfactual reasoning, and synthesizes PubMed literature into structured clinical case reports.
</p>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Phase 1: Biomedical NER](#phase-1-biomedical-ner)
- [Phase 2: Knowledge RAG](#phase-2-knowledge-rag)
- [Phase 3R: Population Evidence](#phase-3r-real-population-evidence--population-aware-re-ranking)
- [Phase 4: Explainable Clinical Reasoning & Differential](#phase-4-explainable-clinical-reasoning--differential)
- [Phase 5: Scribe & Counterfactual Diagnosis Lab](#phase-5-advanced-diagnostic-reasoning--counterfactual-analysis)
- [Phase 6: Literature Intelligence & Case Report Generation](#phase-6-evidence--literature-intelligence--clinical-case-report-generation)
- [Workflow Guide: How & Where to Click](#workflow-guide-how--where-to-click)
- [Frontend Unified Dashboard](#frontend--landing-page)
- [REST API](#rest-api)
- [Setup & Installation](#setup--installation)
- [Running the Pipeline](#running-the-pipeline)
- [Evaluation Results](#evaluation-results)
- [Tech Stack](#tech-stack)
- [License](#license)

---

## Overview

Rare diseases affect over 300 million people worldwide, yet diagnosis takes an average of **5–7 years** due to:

1. **Clinical Complexity** — Scattered phenotype observations in unstructured EHRs
2. **Knowledge Fragmentation** — Evidence distributed across HPO, OMIM, Orphanet, and PubMed
3. **Population Underrepresentation** — Western-centric genomic baselines mischaracterize Indian population variants

This project addresses all three challenges through a unified **6-phase AI pipeline**:

| Phase | Component | Purpose |
|-------|-----------|---------|
| **Phase 1** | BiomedBERT NER | Extract phenotype entities from clinical text |
| **Phase 2** | Semantic RAG | Retrieve candidate diseases via HPO + FAISS vector search |
| **Phase 3** | Population Prior | Bayesian re-ranking with gnomAD (IndiGen unavailable) allele frequencies |
| **Phase 4** | Reasoning & Evidence Fusion | Multi-modal evidence synthesis, differential diagnosis & doctor copilot |
| **Phase 5** | Clinical Scribe & Counterfactuals | Structured EHR normalization & what-if phenotype perturbation lab |
| **Phase 6** | Literature Intelligence & Case Reports | Verified NCBI PubMed literature explorer, phenotype matrix & 11-section case reports |

---

## Architecture

```
Clinical Text
      │
      ▼
┌─────────────────────────┐
│  BiomedBERT NER         │  Token-level BIO tagging -> phenotype mentions
│  (Phase 1, trained)     │  with character offsets + confidence. Test F1 0.7203
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  HPO Normalizer         │  exact -> synonym -> lexical -> semantic (S-PubMedBERT)
│                         │  statuses: exact | synonym | lexical | semantic |
│                         │  ambiguous | unmatched. Never maps unknown text to a term.
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  Phase 2R Retrieval     │  REAL S-PubMedBERT (768-d) embeddings, FAISS exact index,
│  HPO-level matching     │  19,894 active HPO terms · 12,880 diseases
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  Phase 3 re-ranking     │  PROTOTYPE: population tables are placeholder data
│  (Phase 3R pending)     │  (not real IndiGen/gnomAD); no benefit is claimed
└──────────┬──────────────┘
           ▼
   Evidence fusion · reasoning · counterfactuals · literature · reports (Phases 4-6)
```

> **Status (honest):** Phases 1-2 are trained/measured and validated. Phase 3 population priors use **placeholder data**
> and are not yet scientifically meaningful (Phase 3R). BioBERT (baseline NER) is implemented but **not trained**.

---

## Project Structure

```
.
├── configs/
│   └── config.yaml                    # Central configuration (paths, models, hyperparams)
│
├── scripts/
│   ├── download_dataset.py            # Clone BioCreative training data
│   ├── download_hpo_data.py           # Download HPO ontology + disease annotations
│   ├── inspect_dataset.py             # Dataset inspection & statistics
│   ├── run_phase1.py                  # Phase 1 master script (NER training + eval)
│   ├── run_phase2.py                  # Phase 2 master script (KB + embeddings + retrieval)
│   └── run_phase3.py                  # Phase 3 master script (population priors + ranking)
│
├── src/
│   ├── api/
│   │   └── main.py                    # FastAPI REST server (Phase 2 + Phase 3 endpoints)
│   │
│   ├── data/
│   │   └── convert_to_bio.py          # TSV → BIO-tagged dataset conversion
│   │
│   ├── models/
│   │   ├── train_biomedbert.py        # BiomedBERT fine-tuning for phenotype NER
│   │   └── train_biobert.py           # BioBERT baseline fine-tuning
│   │
│   ├── evaluation/
│   │   ├── evaluate_ner.py            # NER precision/recall/F1 evaluation
│   │   ├── evaluate_retrieval.py      # Retrieval recall@K / MRR evaluation
│   │   ├── evaluate_ranking.py        # Ranking ablation evaluation
│   │   └── error_analysis.py          # Error analysis & classification
│   │
│   ├── inference/
│   │   └── predict.py                 # NER inference on raw clinical text
│   │
│   ├── knowledge/
│   │   ├── build_hpo_knowledge_base.py  # HPO ontology + disease KB builder
│   │   └── hpo_normalizer.py            # Phenotype → HPO term mapper
│   │
│   ├── retrieval/
│   │   ├── embed_knowledge_base.py    # Sentence-transformer embedding generation
│   │   ├── build_faiss_index.py       # FAISS index construction
│   │   ├── disease_retriever.py       # Multi-strategy disease retrieval
│   │   └── hpo_search.py              # HPO semantic search
│   │
│   ├── rag/
│   │   └── context_builder.py         # RAG context assembly
│   │
│   ├── population/
│   │   ├── indigen_processor.py       # LEGACY synthetic placeholder (quarantined, unused — see _legacy_synthetic/README.md)
│   │   ├── gnomad_processor.py        # gnomAD allele frequency processor
│   │   ├── variant_normalizer.py      # Variant notation normalization
│   │   ├── frequency_comparator.py    # Population frequency comparison
│   │   └── inspect_population_data.py # Population data inspection
│   │
│   ├── ranking/
│   │   ├── disease_ranker.py          # Multi-component disease ranker
│   │   ├── population_prior.py        # Bayesian population prior engine
│   │   ├── explanation.py             # Evidence-linked explanation generator
│   │   └── tune_weights.py            # Ranking weight optimization
│   │
│   └── pipeline/
│       ├── retrieval_pipeline.py      # End-to-end Phase 2 pipeline
│       └── ranking_pipeline.py        # End-to-end Phase 3 pipeline
│
├── frontend/                          # React + Vite + TailwindCSS landing page
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                    # React Router (/ and /dashboard)
│       ├── styles/index.css           # Master design system tokens
│       ├── components/
│       │   ├── BrandLogo.jsx
│       │   ├── Navbar.jsx
│       │   ├── HeroSection.jsx
│       │   ├── CredibilityStrip.jsx
│       │   ├── ProblemSection.jsx
│       │   ├── WorkflowSection.jsx
│       │   ├── ArchitectureSection.jsx
│       │   ├── EvidenceSection.jsx
│       │   ├── ResearchSection.jsx
│       │   ├── FeaturesSection.jsx
│       │   ├── EvaluationSection.jsx
│       │   ├── CTASection.jsx
│       │   └── Footer.jsx
│       └── pages/
│           ├── LandingPage.jsx
│           └── DashboardPage.jsx
│
├── reports/                           # Evaluation outputs & analysis
│   ├── ner_evaluation_detailed.json
│   ├── ner_model_comparison.csv
│   ├── ranking_ablation.csv
│   ├── ranking_evaluation.json
│   ├── best_ranking_weights.json
│   ├── population_frequency_summary.csv
│   └── ...
│
├── requirements.txt
├── code.html                          # Original landing page design (source of truth)
└── README.md
```

> **Note:** Model weights (`models/`), processed data (`data/`), and `node_modules/` are excluded from the repository due to size. See [Setup & Installation](#setup--installation) for regeneration instructions.

---

## Phase 1: Biomedical NER

**Goal:** Extract phenotype entity mentions from unstructured clinical text.

| Component | Detail |
|-----------|--------|
| **Model** | BiomedBERT (`microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`) |
| **Task** | Token-level BIO tagging (`B-PHENOTYPE`, `I-PHENOTYPE`, `O`) |
| **Dataset** | [BioCreative Clinical Genetics Training Data](https://github.com/Ian-Campbell-Lab/Clinical-Genetics-Training-Data) |
| **Split** | 1,716 train / 227 dev / 227 test |
| **Training** | 4 epochs, lr=2e-5, batch=16, max_len=512 |

### Results

| Metric | Score |
|--------|-------|
| Precision | 0.7193 |
| Recall | 0.7213 |
| **F1 Score** | **0.7203** |
| Accuracy | 0.9069 |

```bash
# Run Phase 1
python scripts/run_phase1.py
```

---

## Phase 2: Knowledge Base + Real Semantic Retrieval (Phase 2R)

| Component | Detail |
|-----------|--------|
| **Knowledge base** | HPO `hp.obo` (release 2026-09-01; 19,894 active + 588 obsolete terms) and HPO annotations `phenotype.hpoa` (2026-09-02) -> **12,880 diseases** (OMIM 8,478 · Orphanet 4,355 · DECIPHER 47) |
| **Primary embedder** | `pritamdeka/S-PubMedBert-MS-MARCO` — 768-d, mean pooling, L2-normalised |
| **Baseline embedder** | `sentence-transformers/all-MiniLM-L6-v2` — 384-d, mean pooling, L2-normalised |
| **Index** | FAISS `IndexFlatIP` (exact cosine), one HPO + one disease index **per model** (never mixed) |
| **Execution** | Real model inference on CPU or GPU via `transformers` (see note below). No random/placeholder vectors anywhere. |

Embeddings live in `data/embeddings/<spubmedbert|minilm>/` with a `manifest.json` (model, dimension, device, timestamp,
source-data versions, SHA-256 checksums); indexes in `data/vector_db/<model>/`. Canonical text is built only from source
data (HPO name + synonyms + definition; disease name + genes + phenotype names). 8 HPO and 332 disease texts exceed the
350-token limit of S-PubMedBERT and are truncated (genes are placed before the phenotype list so they survive).

### Pipeline (single source of truth)

```
Clinical text -> BiomedBERT NER -> HPO normalisation -> real S-PubMedBERT embeddings -> FAISS -> candidate diseases
```

`src/pipeline/retrieval_pipeline.py` is the only phenotype-extraction path; `/api/retrieve`, `/api/rank`, `/api/diagnose`
and the counterfactual lab all use it. Only terms under HP:0000118 *Phenotypic abnormality* are used for retrieval (HPO
modifier terms such as "Recurrent" are reported but not searched).

### Retrieval strategies

| Strategy | Idea |
|---|---|
| `hpo_expansion` | Each phenotype is compared with every HPO term (real HPO embeddings); a disease's score is its best-matching annotated term, sharpened as `exp((cos-1)/tau)`, averaged over phenotypes. `tau = 0.1`, calibrated on a query set disjoint from the evaluation queries (`reports/retrieval_tau_calibration.json`). |
| `hpo_expansion_sym` (**default**) | The score above averaged with a disease->query score (each annotated disease term matched to its closest query phenotype), i.e. a symmetric best-match average. Statistically indistinguishable from `hpo_expansion` on mean MRR (0.832 vs 0.831: better on name queries, slightly worse on synonym queries); chosen because it breaks exact score ties between diseases that annotate every query term. `tau = 0.1`. |
| `mean_vector` | One FAISS search with the mean phenotype embedding against whole-disease embeddings. |
| `per_phenotype_rrf` | Per-phenotype rankings merged with reciprocal-rank fusion (k = 60). |
| `concat_text` | Phenotype text concatenated into one query. |

### HPO normalisation (BioCreative clinician annotations, held-out test split, n = 270)

Semantic threshold (0.88) and margin (0.02) were calibrated on the *train* split only (rule: maximise coverage subject to precision ≥ 0.85).

| Metric | Value |
|---|---|
| Mapped (exact / synonym / lexical / semantic) | 67.8 % (36.0 / 16.7 / 8.5 / 6.7) |
| Precision when mapped | **97.3 %** |
| Ambiguous (candidates returned; correct term among them in 51 of 84) | 31.1 % |
| Unmatched | 1.1 % |
| Overall accuracy (ambiguous/unmatched counted wrong) | 65.9 % |
| Semantic top-5 recall (all phrases) | 86.7 % |

### Retrieval evaluation (simulated patients; `reports/retrieval_evaluation.json`)

500 diseases, 4 phenotypes sampled from each disease's own HPO annotations, strict disease-ID ground truth, identical queries
for all systems. "names" uses preferred HPO names; "synonyms" uses a different surface form of each term.

| System | names R@1 | R@5 | R@10 | MRR | synonyms R@1 | R@10 | MRR | P50 latency |
|---|---|---|---|---|---|---|---|---|
| **S-PubMedBERT `hpo_expansion_sym`** (default) | 0.810 | 0.942 | 0.980 | **0.868** | 0.708 | 0.946 | 0.795 | ~85 ms |
| S-PubMedBERT `hpo_expansion` | 0.764 | 0.948 | 0.980 | 0.846 | 0.730 | 0.966 | **0.815** | ~80 ms |
| MiniLM `hpo_expansion` | 0.666 | 0.880 | 0.932 | 0.763 | 0.520 | 0.858 | 0.642 | ~44 ms |
| MiniLM `hpo_expansion_sym` | 0.546 | 0.798 | 0.878 | 0.653 | 0.414 | 0.782 | 0.536 | ~49 ms |
| TF-IDF lexical baseline | 0.464 | 0.748 | 0.862 | 0.598 | 0.072 | 0.322 | 0.154 | ~3 ms |
| S-PubMedBERT `mean_vector` | 0.048 | 0.140 | 0.208 | 0.100 | 0.016 | 0.116 | 0.052 | ~31 ms |
| MiniLM `mean_vector` | 0.058 | 0.174 | 0.228 | 0.112 | 0.038 | 0.148 | 0.075 | ~13 ms |
| HPO-ID overlap (given oracle IDs, reference) | 0.792 | 0.970 | 0.984 | 0.866 | – | – | – | ~5 ms |

**Limitations of this evaluation:** queries are drawn from the target disease's own annotations, so this measures recovery of a
disease from a partial phenotype set, **not diagnostic accuracy on real patients** (no real cohort with confirmed diagnoses is
available here). Whole-disease dense retrieval (`mean_vector`, `per_phenotype_rrf`) performs far worse than lexical baselines;
the strong result comes from matching at the HPO-term level. MiniLM is a general-domain model and is weaker than S-PubMedBERT.

> **Environment note:** the `sentence_transformers` package (and `datasets`) cannot be imported on the development machine because
> Windows Application Control blocks `pyarrow.dataset`. `src/retrieval/encoder.py` therefore runs the same Transformer + mean-pooling
> (+ L2-normalise) pipeline directly with `transformers`/`torch`. It fails loudly if a model cannot load. NER training/evaluation
> scripts still use `datasets` and need an environment where it imports.

```bash
python scripts/run_phase2.py --rebuild          # KB -> real embeddings -> FAISS -> validation -> evaluation (long on CPU: ~50 min)
python scripts/validate_embeddings.py           # 44 integrity checks, writes reports/embedding_validation.json
python scripts/e2e_pipeline_check.py            # end-to-end check against a running backend
```

---

## Phase 3R: Real Population Evidence + Population-Aware Re-ranking

**What is real:** population evidence is built from public source records only —
**ClinVar** (germline pathogenic / likely-pathogenic variants, GRCh38) joined to **gnomAD v4.1 exome** allele counts
(global and the **gnomAD South Asian** ancestry group), read from the official public VCFs by HTTP range requests (no whole-file download).
Derived tables are produced programmatically from those records; provenance is in `reports/population_data_provenance.json`.

**What is NOT available:** **IndiGen** (CSIR-IGIB) — *access required, unavailable*. No Indian-specific evidence is used. gnomAD South Asian is a
regional comparator, **not IndiGen and not Indian-specific**. Earlier synthetic placeholder tables are quarantined (`*/_legacy_synthetic/`) and unused.

| Component | Detail |
|---|---|
| Variant IDs | canonical `chr:pos:ref:alt` (GRCh38) |
| Gene statistic | `GENE_LEVEL` cumulative allele frequency of ClinVar P/LP variants found (PASS) in gnomAD exomes, per population |
| Signals | empirical CDF of the cumulative frequency (South Asian, global) and of `log2(CAF_SAS / CAF_global)` (defined only when both > 0) |
| Missing data | explicit states `available / not_found / unavailable / not_applicable`; `null`, never a neutral 0.5 |
| Ranking | `final = w_phenotype·phenotype + w_retrieval·retrieval + w_population·(signal − 0.5)`; the last term is 0 without evidence; one config block |
| Ablation | A retrieval+phenotype · B +South Asian · C +South Asian & global comparison · D +IndiGen (**blocked**) · E global-only (extra) |

Population frequency is evidence about how often pathogenic alleles occur in a population. It is **not** a disease probability or a diagnosis.
Results, coverage, weights and the research verdict are in `reports/PHASE_3R_FINAL_COMPLETION_REPORT.md` (generated from the measured reports).

```bash
python scripts/ingest_population.py --clinvar && python scripts/prioritize_genes.py
python scripts/ingest_population.py --run --workers 32 --budget-gb 12 && python scripts/ingest_population.py --crosscheck
python src/evaluation/evaluate_ranking.py && python scripts/build_population_reports.py && python scripts/write_final_report.py
```

---

## Frontend & Landing Page

A **React + Vite + TailwindCSS** single-page application showcasing the project's capabilities.

### Design System

| Token | Value |
|-------|-------|
| Background | `#eaf3f8` (Ocean Blue) |
| Primary | `#000f22` / `#0a2540` |
| Secondary | `#006874` (Teal) |
| Accent | `#99f0fe` (Soft Cyan) |
| Heading Font | Plus Jakarta Sans |
| Body Font | Inter |
| Code Font | JetBrains Mono |

### Routes

| Route | Page |
|-------|------|
| `/` | Master Landing Page |
| `/dashboard` | Diagnostic Workspace (placeholder) |

### 13 Components

Navbar · HeroSection · CredibilityStrip · ProblemSection · WorkflowSection · ArchitectureSection · EvidenceSection · ResearchSection · FeaturesSection · EvaluationSection · CTASection · Footer · BrandLogo

```bash
# Run frontend
cd frontend
npm install
npm run dev   # → http://localhost:5173
```

---

## REST API

FastAPI-powered REST endpoints for phenotype retrieval and disease ranking.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/input/validate` | Quality Gate: Validates clinical relevance & filters profanity |
| `POST` | `/api/input/enhance` | AI Text Enhancement: Refines grammar/abbreviations without altering medical facts |
| `POST` | `/api/retrieve` | Phase 2R: BiomedBERT NER → HPO normalisation → real embeddings → FAISS → candidates. Body `{"clinical_text": ..., "top_k": 10}` |
| `POST` | `/api/rank` | Same retrieval pipeline + Phase 3 re-ranking (prototype population data) |
| `POST` | `/api/diagnose` | End-to-end pipeline (NER → HPO → retrieval → ranking → fusion → reasoning); accepts `clinical_text` or legacy `text` |

### Clinical Input Quality Gate & AI Text Enhancement

The input validation guard (`src/input_guard/`) implements a multi-layer quality gate before running clinical pipeline execution:
1. **Content Safety**: Deterministic filter blocks profanity and spam without hitting the LLM.
2. **Relevance Classification**: Distinguishes valid clinical inputs (e.g. single symptoms "Seizures", "Hypotonia", or full clinical notes) from casual inputs ("hii", "asdfgh", "test").
3. **Grounded AI Enhancement**: Refines clinical phrasing and expands abbreviations (e.g. `pt` → `Patient`, `dev delay` → `developmental delay`) via internal local AI reasoning without inventing unmentioned clinical facts.
4. **User Review Approval**: Gives clinicians full control to review side-by-side original vs. enhanced text with an interactive editor before proceeding to diagnosis.

```bash
# Validate Clinical Input
curl -X POST http://localhost:8000/api/input/validate \
  -H "Content-Type: application/json" \
  -d '{"text": "pt has dev delay and seizures since 2 yrs"}'

# Enhance Clinical Text
curl -X POST http://localhost:8000/api/input/enhance \
  -H "Content-Type: application/json" \
  -d '{"text": "pt has dev delay and seizures since 2 yrs"}'
```

### Example Request

```bash
curl -X POST http://localhost:8000/api/rank \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.",
    "top_k": 10,
    "exp_config": "rag_indigen_gnomad"
  }'
```

### Response Schema

```json
{
  "phenotypes": [...],
  "hpo_terms": [...],
  "retrieved_candidates": [...],
  "ranked_candidates": [...],
  "ranking_explanations": [...]
}
```

```bash
# Start API server
python src/api/main.py   # → http://localhost:8000
```

---

## Setup & Installation

### Secrets

Copy `.env.example` to `.env` and set `GROQ_API_KEY` (used for input enhancement and the grounded explanations/copilot). Never commit keys; `.env` is git-ignored.

**Language model (Groq is the only provider).** The model id lives in `configs/config.yaml` (`llm.model`, currently `openai/gpt-oss-120b`; override with `GROQ_MODEL`). No local model server is needed: the backend starts and retrieval/ranking work without any LLM. If Groq is unreachable, rejects the key, or rate-limits, explanation routes return a clearly labelled deterministic fallback. Note that submitted clinical text is sent to the external provider for these features; assess this against your privacy requirements before real-patient use. The provider enforces a tokens-per-minute limit (about 8,000 on the tested account), so back-to-back large explanation requests may be rate-limited.

**Accounts, storage and security (Phase 7R, accurate).** Users register and sign in (argon2id password hashes; opaque bearer sessions with idle and absolute expiry, revoked on logout). Every `/api/*` route except register/login needs a session, and cases, scenarios, reports and scribe drafts are stored in a database (SQLite for development, PostgreSQL for deployment; Alembic migrations) under the owner's id, so another user's ids behave as "not found". CORS is an allowlist, with body-size limits and per-process rate limits; TLS must be terminated by your proxy or platform. Not provided: email verification, password reset, MFA, multi-instance rate limiting, regulatory compliance. See `docs/DEPLOYMENT.md` and `reports/PHASE_7R_SECURE_DEPLOYMENT_COMPLETION_REPORT.md` (including the public-hosting decision).

Verify a deployment: `python -m unittest tests.test_groq_provider` (mocked + live tests; live ones skip without a key) and `GET /` (reports `llm.status` without secrets).

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- CUDA-capable GPU (recommended for training)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/HemangDubey/Explainable-Rare-Disease-Diagnostic-Assistant-Phenotype-Aware-RAG-.git
cd Explainable-Rare-Disease-Diagnostic-Assistant-Phenotype-Aware-RAG-

# Install Python dependencies
pip install -r requirements.txt

# Run the full pipeline (Phase 1 → 2 → 3)
python scripts/run_phase1.py
python scripts/run_phase2.py
python scripts/run_phase3.py

# Start the API
python src/api/main.py
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Google Colab

Each phase can be run on Google Colab with GPU acceleration. The `scripts/run_phase*.py` master scripts handle dataset download, model training, knowledge base construction, and evaluation automatically.

---

## Evaluation Results

### Phase 1: NER Performance

| Model | Precision | Recall | F1 | Accuracy |
|-------|-----------|--------|----|----------|
| **BiomedBERT** | 0.7193 | 0.7213 | **0.7203** | 0.9069 |

### Phase 2: Retrieval and HPO normalisation

See the Phase 2 section above (`reports/retrieval_evaluation.json`, `reports/retrieval_model_comparison.csv`,
`reports/hpo_normalization_evaluation.json`, `reports/embedding_validation.json`, `reports/retrieval_pipeline_validation.json`).

### Phase 3R: Ranking ablation

See `reports/PHASE_3R_FINAL_COMPLETION_REPORT.md` and `reports/ranking_evaluation.json`.

---

## Phase 4: Explainable Clinical Reasoning & Differential

Phase 4 integrates multi-modal evidence fusion, transparent differential reasoning, and interactive clinical copilot capabilities:

### 1. Evidence Fusion Engine (`src/reasoning/evidence_fusion.py`)
- Fuses clinical inputs across 4 distinct dimensions: Phenotype overlap, S-PubMedBERT semantic similarity, established genetics, and population-frequency evidence (gnomAD global and gnomAD South Asian, each under its own name; IndiGen unavailable; population weight 0).
- Categorizes all clinical observations into **SUPPORTING**, **CONTRADICTING**, **MISSING**, and **NEUTRAL** evidence items with rule-based confidence scoring.

### 2. Differential Diagnosis & Doctor Copilot
- Synthesizes head-to-head comparison matrices explaining why Disease A is prioritized over Disease B.
- Provides an interactive clinician copilot answering case queries with strict grounding on retrieved evidence.

---

## Phase 5: Advanced Diagnostic Reasoning & Counterfactual Analysis

Phase 5 extends the diagnostic architecture with two research modules:

### 1. AI Clinical Scribe (`/api/scribe`)
- Parses unstructured clinical text into structured `ClinicalCase` models.
- Reuses Phase 1 BiomedBERT NER & HPO Normalizer to map clinical spans to canonical `HP:xxxxxxx` terms.
- Detects negated statements (e.g. "No seizures") into `relevant_negatives`.
- Identifies unstated/missing fields under `missing_information` without hallucinating facts.

### 2. Counterfactual Diagnosis Lab (`/api/counterfactual`)
- Executes controlled what-if experiments by modifying phenotype sets (`add`, `remove`, `toggle`, `compare`).
- Reruns Phase 2 Retrieval and Phase 3 Population-Aware Ranking for modified phenotype configurations.
- Calculates exact rank shifts, score deltas, and phenotype ranking sensitivity scores (`phenotype_impact = original_score - counterfactual_score`).
- Generates evidence-grounded, non-causal analytical insights explaining candidate score movements.

#### Phase 5 Endpoints
- `POST /api/scribe` — Extract structured clinical case and HPO terms
- `POST /api/counterfactual` — Execute what-if counterfactual sensitivity analysis
- `POST /api/counterfactual/add` — Add phenotype to what-if case state
- `POST /api/counterfactual/remove` — Remove phenotype from what-if case state
- `POST /api/counterfactual/compare` — Compare two custom case states
- `GET /api/counterfactual/{case_id}` — Retrieve counterfactual experiment history

---

## Phase 6: Evidence & Literature Intelligence + Clinical Case Report Generation

Phase 6 extends the clinical intelligence stack with authentic literature synthesis and structured reporting:

### 1. Evidence & Literature Explorer (`/api/literature/search`, `/api/evidence/*`)
- Queries official NCBI PubMed E-Utilities (`esearch`, `esummary`, `efetch`) using targeted multi-strategy queries (disease-gene, phenotype co-occurrence, and Indian cohort publications).
- **Strict Evidence Integrity**: Zero synthetic/fake PMIDs or hallucinated citations; all articles are fetched directly from PubMed or local disk cache (`data/cache/pubmed/`).
- **Semantic Relevance Scoring**: Automatically ranks abstracts using S-PubMedBERT semantic similarity against case phenotype representations.
- **Evidence Categorization & Strength**: Classifies citations into `Disease Definition`, `Gene-Disease Association`, `Phenotype Evidence`, `Indian Cohort / Population`, `Case Report`, and `Functional Study` with strength ratings (`STRONG`, `MODERATE`, `WEAK`).
- **Phenotype × Literature Evidence Matrix**: Renders a cross-referencing matrix indicating whether patient phenotypes are confirmed (`✓`), equivocal (`?`), or unmentioned (`-`) across retrieved literature.

### 2. Clinical Case Report Generator (`/api/report/generate`, `/api/report/{id}/export`)
- Synthesizes all diagnostic intelligence (Phases 1–6) into a standardized 11-section Clinical Decision Support Case Report:
  1. Patient Presentation & Clinical Narrative
  2. Normalized Phenotype Profile (HPO)
  3. Top Ranked Differential Diagnoses (with composite scores)
  4. Evidence Fusion Breakdown (Phenotype + Retrieval + Population Priors)
  5. Population-frequency context (gnomAD global and South Asian; IndiGen unavailable)
  6. Curated PubMed Literature & Evidence Highlights
  7. Explainable Clinical Reasoning & Mechanism
  8. Differential Diagnosis & Discriminative Features
  9. Counterfactual Sensitivity & Stability
  10. Actionable Diagnostic Workup & Recommendations (Genomic, Biochemical, Multi-disciplinary)
  11. Limitations & Clinical Research Governance
- Includes print-ready HTML export with dedicated print media stylesheets and structured JSON export.

#### Phase 6 Endpoints
- `POST /api/literature/search` — Search PubMed citations with deterministic query builder
- `GET /api/literature/{pmid}` — Fetch authentic metadata and abstract for a PubMed PMID
- `GET /api/evidence/profile/{disease_id}` — Consolidate disease literature profile & stats
- `GET /api/evidence/matrix/{disease_id}` — Generate Phenotype × Literature Evidence Matrix
- `POST /api/report/generate` — Synthesize 11-section Clinical Case Report from active case
- `GET /api/report/{report_id}` — Retrieve generated case report JSON
- `GET /api/report/{report_id}/export` — Export printable medical HTML case report

---

## Workflow Guide: How & Where to Click

Follow this interactive flow to utilize all modules in the unified workspace (`http://localhost:5173/dashboard`):

### 1. Clinical Presentation Input & AI Quality Gate
- Navigate to the **Dashboard** at `http://localhost:5173/dashboard`.
- In the top card **"Patient Clinical Presentation & Physical Exam Findings"**, select one of the quick samples (`Case #1`, `Case #2`, or `Case #3`) or enter unstructured EHR text.
- *(Optional)* Click **"Enhance with AI"** to validate clinical relevance and standardize medical abbreviations, then click **"Apply Enhancement"**.
- Click the primary button: **`[ Run Diagnostic Prioritization ]`**.

### 2. Multi-Modal Diagnostic & Evidence Review
- **Prioritized Candidates & Evidence Tab**: Review ranked disease matches, composite probability tiers, matched HPO terms, and population-frequency evidence (gnomAD global / South Asian; IndiGen shown as unavailable).
- Click **"Explain Diagnosis"** on any candidate to inspect itemized evidence trails (`SUPPORTING`, `CONTRADICTING`, `MISSING`, `NEUTRAL`).
- **Differential Diagnosis Explorer Tab**: Inspect head-to-head comparison matrices showing discriminative clinical features between top candidates.
- **Explainable AI Doctor Copilot Tab**: Ask custom questions (e.g. *"Why was Prader-Willi prioritized over Angelman Syndrome?"*).

### 3. Scribe & Counterfactual Diagnosis Lab
- **AI Clinical Scribe Tab**: Convert complex unstructured clinic notes into structured JSON models with explicit negative findings (`relevant_negatives`) and evidence gaps (`missing_information`).
- **Counterfactual Diagnosis Lab Tab**: Test what-if hypotheses by adding, removing, or toggling phenotypes to observe real-time candidate rank shifts and phenotype sensitivity scores.

### 4. Evidence & Literature Explorer (Phase 6)
- Click the **`Evidence & Literature`** tab in the top navigation bar.
- **Candidate Selector**: Click any prioritized disease candidate pill to load its authentic PubMed citations.
- **Phenotype × Literature Matrix**: Review the interactive cross-referencing matrix (`✓` = confirmed reported, `?` = equivocal/partial, `-` = absent) mapping patient phenotypes to PubMed citations.
- **Evidence Category Filters**: Filter by `Gene-Disease Association`, `Phenotype Evidence`, `🇮🇳 Indian Cohorts`, or `Case Report`.
- **Abstract Modals & Links**: Click **`Read Abstract ↗`** to open verified PubMed abstracts inline or click the title to view the official citation on NCBI PubMed.

### 5. Clinical Case Report Generation (Phase 6)
- Click the **`Clinical Case Report`** tab in the navigation bar.
- Click **`[ Generate Full Case Report ]`** to synthesize the complete 11-section clinical case report.
- Click **`🖨️ Print / Save as PDF`** to generate a printable medical document or **`Export HTML`** to save an offline report.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **NER Model** | BiomedBERT (HuggingFace Transformers) |
| **Embeddings** | S-PubMedBERT / MiniLM via Hugging Face `transformers` |
| **Vector Search** | FAISS |
| **Ontology** | HPO (Human Phenotype Ontology) |
| **Disease DBs** | HPO annotations (OMIM / Orphanet / DECIPHER entries) |
| **Population** | ClinVar + gnomAD v4.1 (global, South Asian); IndiGen unavailable |
| **Backend API** | FastAPI + Uvicorn |
| **Frontend** | React 18 + Vite + TailwindCSS 3 |
| **Routing** | React Router DOM v6 |
| **Deep Learning** | PyTorch + HuggingFace |

---

## License

This project is developed as a **research prototype** for clinical decision support.

> ⚠️ **Disclaimer:** This is NOT a substitute for professional medical diagnosis. All outputs are for research and educational purposes only.

---

<p align="center">
  <sub>Built with 🧬 by <a href="https://github.com/HemangDubey">Hemang Dubey</a></sub>
</p>
