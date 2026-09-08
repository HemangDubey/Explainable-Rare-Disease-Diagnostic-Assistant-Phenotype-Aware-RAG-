"""Schemas for Literature Intelligence Subsystem (Phase 6)."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EvidenceCategory(str, Enum):
    DISEASE_DEFINITION = "Disease Definition"
    GENE_DISEASE = "Gene-Disease Association"
    PHENOTYPE_EVIDENCE = "Phenotype Evidence"
    INDIAN_COHORT = "Indian Cohort / Population"
    CASE_REPORT = "Case Report"
    FUNCTIONAL_STUDY = "Functional Study"
    GENERAL_REVIEW = "General Clinical Review"


class EvidenceStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class PhenotypeMatchStatus(str, Enum):
    CONFIRMED = "✓"      # Directly matched/confirmed in paper
    ABSENT = "-"         # Absent or unmentioned
    EQUIVOCAL = "?"      # Equivocal or partial association


class PubMedArticle(BaseModel):
    pmid: str = Field(..., description="PubMed ID")
    title: str = Field(..., description="Article Title")
    abstract: str = Field(default="", description="Abstract Text")
    journal: str = Field(default="", description="Journal Name")
    pub_year: Optional[str] = Field(default=None, description="Publication Year")
    authors: List[str] = Field(default_factory=list, description="Author List")
    doi: Optional[str] = Field(default=None, description="Digital Object Identifier")
    url: str = Field(default="", description="PubMed URL")
    evidence_category: EvidenceCategory = Field(
        default=EvidenceCategory.GENERAL_REVIEW,
        description="Assigned Evidence Category"
    )
    evidence_strength: EvidenceStrength = Field(
        default=EvidenceStrength.MODERATE,
        description="Assigned Evidence Strength"
    )
    relevance_score: float = Field(
        default=0.0,
        description="Semantic relevance score (0.0 - 1.0)"
    )
    matched_phenotypes: List[str] = Field(
        default_factory=list,
        description="Phenotypes detected in title or abstract"
    )
    matched_genes: List[str] = Field(
        default_factory=list,
        description="Genes mentioned in title or abstract"
    )
    is_indian_cohort: bool = Field(
        default=False,
        description="Whether study discusses Indian or South Asian patient cohort"
    )


class LiteratureSearchRequest(BaseModel):
    disease_id: Optional[str] = Field(None, description="OMIM or Orphanet Disease ID")
    disease_name: str = Field(..., description="Disease Name to query")
    genes: List[str] = Field(default_factory=list, description="Associated genes")
    phenotypes: List[str] = Field(default_factory=list, description="Patient phenotype terms")
    max_results: int = Field(default=10, ge=1, le=30, description="Max articles to fetch")
    custom_query: Optional[str] = Field(None, description="Optional clinician-crafted PubMed search query")


class PhenotypeMatrixRow(BaseModel):
    phenotype: str = Field(..., description="Phenotype description or HPO term")
    hpo_id: Optional[str] = Field(None, description="HPO Identifier if mapped")
    paper_statuses: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of PMID to status ('✓', '-', '?')"
    )
    evidence_count: int = Field(default=0, description="Count of supporting papers")


class EvidenceMatrixResponse(BaseModel):
    disease_id: str
    disease_name: str
    pmids: List[str]
    articles: List[PubMedArticle]
    matrix: List[PhenotypeMatrixRow]


class DiseaseEvidenceProfile(BaseModel):
    disease_id: str
    disease_name: str
    total_articles: int
    strong_evidence_count: int
    moderate_evidence_count: int
    weak_evidence_count: int
    category_breakdown: Dict[str, int]
    top_articles: List[PubMedArticle]
    has_indian_literature: bool
    indian_cohort_articles: List[PubMedArticle]
    phenotype_coverage_pct: float
