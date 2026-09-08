"""Generates Phenotype × Literature Evidence Matrix for candidate diseases."""

import re
from typing import List, Dict, Any, Optional
from src.literature.schemas import (
    PubMedArticle,
    PhenotypeMatrixRow,
    EvidenceMatrixResponse,
    PhenotypeMatchStatus
)


class EvidenceMatrixBuilder:
    """Builds a structured 2D matrix mapping each patient phenotype against retrieved literature."""

    @classmethod
    def build_matrix(
        cls,
        disease_id: str,
        disease_name: str,
        phenotypes: List[Dict[str, Any]],  # e.g., [{"text": "hypotonia", "hpo_id": "HP:0001252"}] or List[str]
        articles: List[PubMedArticle]
    ) -> EvidenceMatrixResponse:
        """Constructs the Phenotype × Literature matrix."""
        pmids = [a.pmid for a in articles]
        matrix_rows: List[PhenotypeMatrixRow] = []

        # Normalize phenotypes format
        normalized_pts = []
        for p in phenotypes:
            if isinstance(p, dict):
                pt_text = p.get("text") or p.get("phenotype") or p.get("name", "")
                hpo_id = p.get("hpo_id") or p.get("id")
                normalized_pts.append((pt_text, hpo_id))
            elif isinstance(p, str):
                normalized_pts.append((p, None))

        for pt_text, hpo_id in normalized_pts:
            clean_pt = pt_text.lower().strip()
            row_statuses: Dict[str, str] = {}
            evidence_count = 0

            # Keywords for equivocal/questionable match
            equivocal_keywords = ["may present", "atypical", "variable", "isolated", "rarely"]

            for article in articles:
                text = f"{article.title} {article.abstract}".lower()

                # Check direct match
                if clean_pt in text:
                    # Check if phrased equivocally
                    is_equivocal = any(eq in text for eq in equivocal_keywords)
                    status = PhenotypeMatchStatus.EQUIVOCAL.value if is_equivocal else PhenotypeMatchStatus.CONFIRMED.value
                    row_statuses[article.pmid] = status
                    evidence_count += 1
                else:
                    # Check partial/word match
                    words = [w for w in re.split(r'\s+', clean_pt) if len(w) > 3]
                    if len(words) > 1 and all(w in text for w in words):
                        row_statuses[article.pmid] = PhenotypeMatchStatus.CONFIRMED.value
                        evidence_count += 1
                    elif words and any(w in text for w in words):
                        row_statuses[article.pmid] = PhenotypeMatchStatus.EQUIVOCAL.value
                    else:
                        row_statuses[article.pmid] = PhenotypeMatchStatus.ABSENT.value

            matrix_rows.append(
                PhenotypeMatrixRow(
                    phenotype=pt_text,
                    hpo_id=hpo_id,
                    paper_statuses=row_statuses,
                    evidence_count=evidence_count
                )
            )

        return EvidenceMatrixResponse(
            disease_id=disease_id,
            disease_name=disease_name,
            pmids=pmids,
            articles=articles,
            matrix=matrix_rows
        )
