"""Module initialization for src/literature/."""

from src.literature.schemas import (
    PubMedArticle,
    LiteratureSearchRequest,
    PhenotypeMatrixRow,
    EvidenceMatrixResponse,
    DiseaseEvidenceProfile,
    EvidenceCategory,
    EvidenceStrength,
    PhenotypeMatchStatus
)
from src.literature.pubmed_client import PubMedClient
from src.literature.query_builder import PubMedQueryBuilder
from src.literature.cache import LiteratureCache
from src.literature.relevance import LiteratureRelevanceScorer

__all__ = [
    "PubMedArticle",
    "LiteratureSearchRequest",
    "PhenotypeMatrixRow",
    "EvidenceMatrixResponse",
    "DiseaseEvidenceProfile",
    "EvidenceCategory",
    "EvidenceStrength",
    "PhenotypeMatchStatus",
    "PubMedClient",
    "PubMedQueryBuilder",
    "LiteratureCache",
    "LiteratureRelevanceScorer"
]
