<p align="center">
  <img src="https://lh3.googleusercontent.com/aida/AEtjO1WsvG4PmtCG5os6CRAflm_m7FddHjQ1303ktfydHJYjv73FM4gZdW8u-WsJuxbsBABuo5yixcrlsh4usHyJ1WM1hKOJ6Zb9GkurAKXxLYdnXVVhjoRkgWmx8A9C6MGG4mS3TN3aahW9_WiX8r03km6-YLg3AMyJ1gU0k-Xbi8sKH6RceS4hSiPgJN6baSnx3yGLjB7_Mxx9cDA8TAO1ltc5C60hM9RUr_z2u-6KCczeC4ccZYNNsweV_g" width="120" alt="ERDDA Logo">
</p>

<h1 align="center">Explainable Rare-Disease Diagnostic Assistant</h1>
<h3 align="center">Phenotype-Aware RAG with Indian Population Priors</h3>

<p align="center">
  <a href="#architecture"><img src="https://img.shields.io/badge/Pipeline-3_Phase-006874?style=for-the-badge" alt="3 Phase Pipeline"></a>
  <a href="#phase-1-biomedical-ner"><img src="https://img.shields.io/badge/NER_F1-0.7203-0a2540?style=for-the-badge" alt="NER F1"></a>
  <a href="#phase-2-knowledge-rag"><img src="https://img.shields.io/badge/HPO_Terms-20%2C482-006874?style=for-the-badge" alt="HPO Terms"></a>
  <a href="#phase-3-population-priors"><img src="https://img.shields.io/badge/IndiGen-Population_Aware-99f0fe?style=for-the-badge&labelColor=0a2540" alt="Population Aware"></a>
</p>

<p align="center">
  An evidence-driven diagnostic assistant that extracts clinical phenotypes from unstructured text, retrieves rare-disease knowledge via semantic search, incorporates Indian population genomic priors, and generates transparent, evidence-linked diagnostic insights.
</p>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Phase 1: Biomedical NER](#phase-1-biomedical-ner)
- [Phase 2: Knowledge RAG](#phase-2-knowledge-rag)
- [Phase 3: Population Priors](#phase-3-population-priors)
- [Frontend & Landing Page](#frontend--landing-page)
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

This project addresses all three challenges through a **3-phase AI pipeline**:

| Phase | Component | Purpose |
|-------|-----------|---------|
| **Phase 1** | BiomedBERT NER | Extract phenotype entities from clinical text |
| **Phase 2** | Semantic RAG | Retrieve candidate diseases via HPO + FAISS vector search |
| **Phase 3** | Population Prior | Bayesian re-ranking with IndiGen & gnomAD allele frequencies |

---

## Architecture

```
Clinical Text
      │
      ▼
┌─────────────────────────┐
│   Phase 1: BiomedBERT   │  Token-level NER → Phenotype spans
│   Phenotype NER         │  Entity-level F1: 0.7203
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   HPO Normalizer        │  String → HP:xxxxxxx ontology linking
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   Phase 2: S-PubMedBERT │  Dense vector retrieval (dim=768)
│   + FAISS RAG           │  20,482 HPO terms · 12,880 diseases
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   Phase 3: IndiGen      │  Bayesian re-weighting with
│   Population Prior      │  Indian allele frequencies
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   Explainable Output    │  Ranked candidates + evidence trails
│   + REST API            │  + phenotype overlap + population priors
└─────────────────────────┘
```

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
│   │   ├── indigen_processor.py       # IndiGen allele frequency processor
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

## Phase 2: Knowledge RAG

**Goal:** Normalize extracted phenotypes to HPO terms and retrieve candidate diseases via semantic vector search.

| Component | Detail |
|-----------|--------|
| **Knowledge Base** | 20,482 HPO terms + 12,880 disease records |
| **Embedding Model** | S-PubMedBERT (`pritamdeka/S-PubMedBert-MS-MARCO`, dim=768) |
| **Vector Index** | FAISS flat inner-product index |
| **Retrieval Strategy** | Mean vector aggregation across detected phenotype embeddings |

### Pipeline Flow

```
Clinical Text → BiomedBERT NER → Phenotype Spans
    → HPO Normalizer → Canonical HP:xxxxxxx Terms
    → S-PubMedBERT Embeddings → FAISS Search
    → Top-K Candidate Diseases → RAG Context
```

```bash
# Run Phase 2
python scripts/run_phase2.py
```

---

## Phase 3: Population Priors

**Goal:** Incorporate Indian population genomic allele frequencies to re-rank candidate diseases using Bayesian posterior adjustment.

| Component | Detail |
|-----------|--------|
| **IndiGen** | Indian population allele frequency data (1,029 WGS samples) |
| **gnomAD** | Global allele frequency baseline |
| **Re-Ranking** | Multi-component weighted scoring: HPO overlap (50%) + Retrieval (35%) + Population prior (15%) |
| **Ablation** | RAG-only → +IndiGen → +gnomAD baseline comparison |

### Scoring Formula

```
Final_Score = w_hpo × HPO_Overlap + w_ret × Retrieval_Sim + w_pop × Population_Prior
```

Where `Population_Prior = P(Disease | IndiGen_AF) / P(Disease | gnomAD_AF)`

```bash
# Run Phase 3
python scripts/run_phase3.py
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
| `POST` | `/api/retrieve` | Phase 2: NER → HPO → FAISS → Candidates |
| `POST` | `/api/rank` | Phase 3: Full pipeline with population re-ranking |
| `POST` | `/api/diagnose` | End-to-End Diagnostic Pipeline (Phases 1–5) |

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

### Phase 2: Knowledge Base Statistics

| Metric | Value |
|--------|-------|
| HPO Terms | 20,482 |
| Disease Records | 12,880 |
| Embedding Dimension | 768 |
| Embedding Model | S-PubMedBERT |

### Phase 3: Ranking Ablation

| Configuration | Description |
|---------------|-------------|
| Experiment A | RAG-Only baseline |
| Experiment B | RAG + IndiGen Indian prior |
| Experiment C | RAG + IndiGen + gnomAD global baseline |

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
  5. Indian Population Genetics Context (IndiGen & gnomAD SAS)
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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **NER Model** | BiomedBERT (HuggingFace Transformers) |
| **Embeddings** | S-PubMedBERT (Sentence-Transformers) |
| **Vector Search** | FAISS |
| **Ontology** | HPO (Human Phenotype Ontology) |
| **Disease DBs** | OMIM, Orphanet, Monarch Initiative |
| **Population** | IndiGen, gnomAD |
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
