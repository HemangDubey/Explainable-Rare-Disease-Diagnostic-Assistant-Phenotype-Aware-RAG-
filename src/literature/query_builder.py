"""Deterministic query builder for PubMed NCBI searches."""

import re
from typing import List, Optional


class PubMedQueryBuilder:
    """Builds targeted, high-precision PubMed search queries for rare diseases."""

    @staticmethod
    def clean_term(term: str) -> str:
        """Removes punctuation and illegal search chars."""
        cleaned = re.sub(r'[^\w\s\-]', ' ', term)
        return " ".join(cleaned.split())

    @classmethod
    def build_disease_query(cls, disease_name: str, limit_recent_years: int = 15) -> str:
        """Standard disease overview / definition query."""
        clean_name = cls.clean_term(disease_name)
        return f'"{clean_name}"[Title/Abstract]'

    @classmethod
    def build_disease_gene_query(cls, disease_name: str, genes: List[str]) -> str:
        """High-precision query combining disease name with associated pathogenic genes."""
        clean_name = cls.clean_term(disease_name)
        if not genes:
            return cls.build_disease_query(disease_name)

        clean_genes = [cls.clean_term(g) for g in genes if g.strip()]
        if not clean_genes:
            return cls.build_disease_query(disease_name)

        genes_clause = " OR ".join([f'"{g}"[Title/Abstract]' for g in clean_genes[:5]])
        return f'("{clean_name}"[Title/Abstract]) AND ({genes_clause})'

    @classmethod
    def build_phenotype_query(cls, disease_name: str, phenotypes: List[str]) -> str:
        """Queries disease co-occurrence with specific clinical phenotypes."""
        clean_name = cls.clean_term(disease_name)
        if not phenotypes:
            return cls.build_disease_query(disease_name)

        clean_pts = [cls.clean_term(p) for p in phenotypes if p.strip()]
        if not clean_pts:
            return cls.build_disease_query(disease_name)

        # Combine top phenotypes with OR
        pt_clause = " OR ".join([f'"{p}"[Title/Abstract]' for p in clean_pts[:6]])
        return f'("{clean_name}"[Title/Abstract]) AND ({pt_clause})'

    @classmethod
    def build_indian_cohort_query(cls, disease_name: str) -> str:
        """Targets publications studying Indian, South Asian, or IndiGen cohorts for the disease."""
        clean_name = cls.clean_term(disease_name)
        geo_terms = '("India"[Title/Abstract] OR "Indian"[Title/Abstract] OR "South Asian"[Title/Abstract] OR "IndiGen"[Title/Abstract])'
        return f'("{clean_name}"[Title/Abstract]) AND {geo_terms}'

    @classmethod
    def build_single_phenotype_query(cls, disease_name: str, phenotype: str) -> str:
        """Query for verifying a specific phenotype against the disease."""
        clean_name = cls.clean_term(disease_name)
        clean_pt = cls.clean_term(phenotype)
        return f'("{clean_name}"[Title/Abstract]) AND ("{clean_pt}"[Title/Abstract])'
