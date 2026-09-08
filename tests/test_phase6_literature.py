"""Unit and integration tests for Phase 6 Literature Intelligence and Evidence Explorer."""

from src.literature.schemas import PubMedArticle, EvidenceCategory, EvidenceStrength, PhenotypeMatchStatus
from src.literature.cache import LiteratureCache
from src.literature.query_builder import PubMedQueryBuilder
from src.evidence.evidence_classifier import EvidenceClassifier
from src.evidence.evidence_matrix import EvidenceMatrixBuilder
from src.evidence.evidence_profile import DiseaseEvidenceProfileBuilder


def test_query_builder_disease_and_genes():
    q = PubMedQueryBuilder.build_disease_gene_query("Prader-Willi Syndrome", ["SNRPN", "MAGEL2"])
    assert "Prader-Willi Syndrome" in q
    assert "SNRPN" in q
    assert "MAGEL2" in q


def test_query_builder_indian_cohort():
    q = PubMedQueryBuilder.build_indian_cohort_query("Gaucher Disease")
    assert "Gaucher Disease" in q
    assert "India" in q
    assert "IndiGen" in q


def test_cache_mechanism(tmp_path):
    cache = LiteratureCache(cache_dir=str(tmp_path))
    query = "hypotonia in infant"
    pmids = ["12345678", "87654321"]

    assert cache.get_query_results(query) is None
    cache.set_query_results(query, pmids)
    assert cache.get_query_results(query) == pmids

    art_dict = {"pmid": "12345678", "title": "Test Title", "abstract": "Test Abstract"}
    cache.set_article("12345678", art_dict)
    assert cache.get_article("12345678") == art_dict


def test_evidence_classifier():
    article = PubMedArticle(
        pmid="12345",
        title="Clinical features and novel mutation in an Indian cohort with Gaucher disease",
        abstract="We describe 15 Indian pediatric patients presenting with hepatosplenomegaly and hypotonia with GBA mutation.",
        relevance_score=0.82
    )

    classified = EvidenceClassifier.classify_article(
        article=article,
        disease_name="Gaucher Disease",
        patient_phenotypes=["hypotonia", "seizures"],
        genes=["GBA"]
    )

    assert classified.is_indian_cohort is True
    assert classified.evidence_category == EvidenceCategory.INDIAN_COHORT
    assert classified.evidence_strength == EvidenceStrength.STRONG
    assert "hypotonia" in classified.matched_phenotypes
    assert "GBA" in classified.matched_genes


def test_evidence_matrix_builder():
    articles = [
        PubMedArticle(
            pmid="111",
            title="Hypotonia and short stature in syndromic patients",
            abstract="Frequent findings include marked hypotonia and short stature.",
            relevance_score=0.75
        ),
        PubMedArticle(
            pmid="222",
            title="Recurrent seizures in developmental delay",
            abstract="Patient exhibited intractable seizures.",
            relevance_score=0.70
        )
    ]

    phenotypes = [
        {"text": "hypotonia", "hpo_id": "HP:0001252"},
        {"text": "seizures", "hpo_id": "HP:0001250"}
    ]

    matrix_res = EvidenceMatrixBuilder.build_matrix(
        disease_id="OMIM:176270",
        disease_name="Prader-Willi Syndrome",
        phenotypes=phenotypes,
        articles=articles
    )

    assert len(matrix_res.matrix) == 2
    hypotonia_row = matrix_res.matrix[0]
    assert hypotonia_row.phenotype == "hypotonia"
    assert hypotonia_row.paper_statuses["111"] == PhenotypeMatchStatus.CONFIRMED.value
    assert hypotonia_row.paper_statuses["222"] == PhenotypeMatchStatus.ABSENT.value


def test_disease_evidence_profile_builder():
    articles = [
        PubMedArticle(
            pmid="111",
            title="Prader-Willi syndrome case in India",
            abstract="Indian cohort study with hypotonia.",
            evidence_category=EvidenceCategory.INDIAN_COHORT,
            evidence_strength=EvidenceStrength.STRONG,
            is_indian_cohort=True,
            matched_phenotypes=["hypotonia"]
        )
    ]

    profile = DiseaseEvidenceProfileBuilder.build_profile(
        disease_id="OMIM:176270",
        disease_name="Prader-Willi Syndrome",
        articles=articles,
        patient_phenotypes=["hypotonia", "seizures"]
    )

    assert profile.total_articles == 1
    assert profile.strong_evidence_count == 1
    assert profile.has_indian_literature is True
    assert profile.phenotype_coverage_pct == 50.0
