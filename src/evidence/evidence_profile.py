"""Evidence Profile builder aggregating complete literature intelligence for a candidate disease."""

from typing import List, Dict, Any
from src.literature.schemas import (
    PubMedArticle,
    DiseaseEvidenceProfile,
    EvidenceStrength,
    EvidenceCategory
)


class DiseaseEvidenceProfileBuilder:
    """Consolidates categorized articles into a comprehensive clinical literature evidence profile."""

    @classmethod
    def build_profile(
        cls,
        disease_id: str,
        disease_name: str,
        articles: List[PubMedArticle],
        patient_phenotypes: List[str]
    ) -> DiseaseEvidenceProfile:
        total = len(articles)
        strong_cnt = sum(1 for a in articles if a.evidence_strength == EvidenceStrength.STRONG)
        mod_cnt = sum(1 for a in articles if a.evidence_strength == EvidenceStrength.MODERATE)
        weak_cnt = sum(1 for a in articles if a.evidence_strength == EvidenceStrength.WEAK)

        cat_breakdown: Dict[str, int] = {}
        for a in articles:
            cat_val = a.evidence_category.value
            cat_breakdown[cat_val] = cat_breakdown.get(cat_val, 0) + 1

        indian_articles = [a for a in articles if a.is_indian_cohort]

        # Calculate phenotype coverage percentage
        covered_pts = set()
        for a in articles:
            for pt in a.matched_phenotypes:
                covered_pts.add(pt.lower().strip())

        total_pts = len([p for p in patient_phenotypes if p.strip()])
        coverage_pct = round((len(covered_pts) / total_pts * 100.0), 1) if total_pts > 0 else 0.0

        # Sort top articles by relevance and strength
        sorted_articles = sorted(
            articles,
            key=lambda x: (
                1 if x.evidence_strength == EvidenceStrength.STRONG else (0.5 if x.evidence_strength == EvidenceStrength.MODERATE else 0),
                x.relevance_score
            ),
            reverse=True
        )

        return DiseaseEvidenceProfile(
            disease_id=disease_id,
            disease_name=disease_name,
            total_articles=total,
            strong_evidence_count=strong_cnt,
            moderate_evidence_count=mod_cnt,
            weak_evidence_count=weak_cnt,
            category_breakdown=cat_breakdown,
            top_articles=sorted_articles[:5],
            has_indian_literature=len(indian_articles) > 0,
            indian_cohort_articles=indian_articles,
            phenotype_coverage_pct=coverage_pct
        )
