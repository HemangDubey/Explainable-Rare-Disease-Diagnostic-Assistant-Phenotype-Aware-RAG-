"""Classifies literature into evidence categories and determines evidence strength."""

import re
from typing import List, Tuple
from src.literature.schemas import PubMedArticle, EvidenceCategory, EvidenceStrength


class EvidenceClassifier:
    """Classifies PubMed articles based on title, abstract text, publication type, and relevance."""

    INDIAN_KEYWORDS = [
        r'\bindia\b', r'\bindian\b', r'\bsouth asian\b', r'\bindigen\b',
        r'\baiims\b', r'\bpgimer\b', r'\bdelhi\b', r'\bmumbai\b', r'\bchennai\b',
        r'\bbengaluru\b', r'\bhyderabad\b', r'\bkarnataka\b', r'\bmaharashtra\b'
    ]

    GENE_KEYWORDS = [
        r'\bmutation\b', r'\bvariant\b', r'\bpathogenic\b', r'\bexome\b',
        r'\bsequencing\b', r'\bnovel variant\b', r'\bcompound heterozygous\b',
        r'\bhomozygous\b', r'\bheterozygous\b', r'\bgene\b'
    ]

    CASE_KEYWORDS = [
        r'\bcase report\b', r'\bpatient presented\b', r'\breport a case\b',
        r'\ba \d+-year-old\b', r'\ba \d+-month-old\b', r'\bcase series\b',
        r'\bclinical presentation\b'
    ]

    FUNCTIONAL_KEYWORDS = [
        r'\bin vitro\b', r'\bin vivo\b', r'\bmouse model\b', r'\bfunctional assay\b',
        r'\bmechanism\b', r'\bpathophysiology\b', r'\bknockout\b', r'\bmolecular basis\b'
    ]

    PHENOTYPE_KEYWORDS = [
        r'\bphenotype\b', r'\bphenotypic\b', r'\bclinical feature\b',
        r'\bspectrum\b', r'\bmanifestation\b', r'\bsymptom\b', r'\bfindings\b'
    ]

    REVIEW_KEYWORDS = [
        r'\breview\b', r'\bconsensus\b', r'\bguideline\b', r'\bdiagnostic criteria\b',
        r'\boverview\b', r'\bupdate\b', r'\bmanagement\b'
    ]

    @classmethod
    def classify_article(
        cls,
        article: PubMedArticle,
        disease_name: str,
        patient_phenotypes: List[str],
        genes: List[str]
    ) -> PubMedArticle:
        """Assigns category, strength, matched phenotypes, and Indian cohort flag."""
        combined_text = f"{article.title} {article.abstract}".lower()

        # Check Indian cohort
        is_indian = any(re.search(pat, combined_text) for pat in cls.INDIAN_KEYWORDS)
        article.is_indian_cohort = is_indian

        # Match phenotypes in text
        matched_pts = []
        for pt in patient_phenotypes:
            clean_pt = pt.lower().strip()
            if clean_pt and len(clean_pt) > 2:
                # Check for direct word presence or stem
                words = [w for w in re.split(r'\s+', clean_pt) if len(w) > 3]
                if clean_pt in combined_text or (words and all(w in combined_text for w in words)):
                    matched_pts.append(pt)
        article.matched_phenotypes = matched_pts

        # Match genes in text
        matched_g = []
        for g in genes:
            clean_g = g.lower().strip()
            if clean_g and re.search(r'\b' + re.escape(clean_g) + r'\b', combined_text):
                matched_g.append(g)
        article.matched_genes = matched_g

        # Determine Category
        if is_indian:
            article.evidence_category = EvidenceCategory.INDIAN_COHORT
        elif any(re.search(p, combined_text) for p in cls.GENE_KEYWORDS) and (matched_g or "mutation" in combined_text):
            article.evidence_category = EvidenceCategory.GENE_DISEASE
        elif any(re.search(p, combined_text) for p in cls.CASE_KEYWORDS):
            article.evidence_category = EvidenceCategory.CASE_REPORT
        elif any(re.search(p, combined_text) for p in cls.FUNCTIONAL_KEYWORDS):
            article.evidence_category = EvidenceCategory.FUNCTIONAL_STUDY
        elif matched_pts or any(re.search(p, combined_text) for p in cls.PHENOTYPE_KEYWORDS):
            article.evidence_category = EvidenceCategory.PHENOTYPE_EVIDENCE
        elif any(re.search(p, combined_text) for p in cls.REVIEW_KEYWORDS):
            article.evidence_category = EvidenceCategory.DISEASE_DEFINITION
        else:
            article.evidence_category = EvidenceCategory.GENERAL_REVIEW

        # Determine Strength
        # Based on relevance score, matched evidence, and category
        score = article.relevance_score
        has_phenotypes = len(matched_pts) > 0
        has_genes = len(matched_g) > 0

        if score >= 0.75 or (has_phenotypes and has_genes) or (is_indian and (has_phenotypes or score >= 0.65)):
            article.evidence_strength = EvidenceStrength.STRONG
        elif score >= 0.50 or has_phenotypes or has_genes:
            article.evidence_strength = EvidenceStrength.MODERATE
        elif score > 0.25:
            article.evidence_strength = EvidenceStrength.WEAK
        else:
            article.evidence_strength = EvidenceStrength.UNKNOWN

        return article
