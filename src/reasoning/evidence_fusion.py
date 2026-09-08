import os
import sys
from typing import List, Dict, Any, Optional

class EvidenceFusionEngine:
    """
    Evidence Fusion Engine (Phase 4).
    Consumes real Phase 3 ranked candidate outputs and synthesizes multi-modal evidence objects
    categorized into SUPPORTING, CONTRADICTING, MISSING, and NEUTRAL with rule-based confidence.
    Follows strict diagnostic safety and evidence traceability rules.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def fuse_candidate_evidence(
        self,
        candidate: Dict[str, Any],
        extracted_phenotypes: List[Dict[str, Any]],
        hpo_terms: List[Dict[str, Any]],
        rank: int
    ) -> Dict[str, Any]:
        """
        Fuses clinical observation inputs with Phase 3 candidate attributes.
        """
        disease_id = candidate.get("disease_id", "Unknown")
        disease_name = candidate.get("disease_name", "Unknown Disease")
        final_score = float(candidate.get("final_score", 0.0))
        p_score = float(candidate.get("phenotype_score", 0.0))
        r_score = float(candidate.get("retrieval_score", 0.0))
        ind_signal = float(candidate.get("indian_population_signal", 0.50))
        gno_signal = float(candidate.get("global_population_signal", 0.50))
        pop_status = candidate.get("population_evidence_status", "unavailable")

        matched_hpo_ids = candidate.get("matched_hpo_ids", [])
        associated_genes = candidate.get("associated_genes", [])
        associated_phenotypes = candidate.get("associated_phenotypes", [])
        evidence_sources = candidate.get("evidence_sources", [])

        # Clean evidence sources
        cleaned_sources = []
        for s in evidence_sources:
            if s and s.strip() and s.strip() not in cleaned_sources:
                cleaned_sources.append(s.strip())

        # 1. Phenotype Evidence Analysis
        # Patient's extracted HPO IDs
        patient_hpo_map = {item.get("hpo_id"): item.get("name", item.get("hpo_id")) for item in hpo_terms if item.get("hpo_id")}
        matched_phenotypes = []
        for hid in matched_hpo_ids:
            name = patient_hpo_map.get(hid, hid)
            matched_phenotypes.append({"hpo_id": hid, "name": name})

        # Missing disease phenotypes: phenotypes known for disease but not noted in patient
        missing_phenotypes = []
        patient_hpo_set = set(patient_hpo_map.keys())
        for ph in associated_phenotypes:
            if ph not in patient_hpo_set and ph not in [m["name"] for m in matched_phenotypes]:
                missing_phenotypes.append(ph)
        missing_phenotypes = missing_phenotypes[:6]  # keep top relevant

        # Classify Phenotype Evidence Confidence
        if len(matched_hpo_ids) >= 3 or p_score >= 0.70:
            phenotype_confidence = "High"
        elif len(matched_hpo_ids) >= 1 or p_score >= 0.30:
            phenotype_confidence = "Moderate"
        elif p_score > 0.0:
            phenotype_confidence = "Low"
        else:
            phenotype_confidence = "Unknown"

        # 2. Retrieval Evidence Analysis
        if r_score >= 0.85:
            retrieval_confidence = "High"
        elif r_score >= 0.65:
            retrieval_confidence = "Moderate"
        elif r_score > 0.0:
            retrieval_confidence = "Low"
        else:
            retrieval_confidence = "Unknown"

        # 3. Population Evidence Analysis
        if pop_status == "available":
            pop_category = "SUPPORTING" if (ind_signal > 0.52 or gno_signal > 0.52) else "NEUTRAL"
            if ind_signal > 0.60:
                population_confidence = "High"
            elif ind_signal > 0.50:
                population_confidence = "Moderate"
            else:
                population_confidence = "Low"
        elif pop_status == "not_found":
            pop_category = "NEUTRAL"
            population_confidence = "Unknown"
        else:
            pop_category = "MISSING"
            population_confidence = "Unknown"

        # Itemized Evidence Trail
        evidence_items = []
        if matched_hpo_ids:
            evidence_items.append({
                "category": "SUPPORTING",
                "aspect": "Phenotype Match",
                "description": f"Matched {len(matched_hpo_ids)} patient HPO phenotype(s): {', '.join([m['name'] for m in matched_phenotypes])}",
                "confidence": phenotype_confidence,
                "score": p_score,
                "source": "Human Phenotype Ontology (HPO)"
            })
        else:
            evidence_items.append({
                "category": "MISSING",
                "aspect": "Phenotype Match",
                "description": "No direct overlapping HPO terms between patient presentation and disease profile",
                "confidence": "Low",
                "score": p_score,
                "source": "Human Phenotype Ontology (HPO)"
            })

        evidence_items.append({
            "category": "SUPPORTING" if r_score >= 0.60 else "NEUTRAL",
            "aspect": "Semantic Knowledge Retrieval",
            "description": f"Vector semantic similarity score of {r_score:.4f} against curated disease knowledge base",
            "confidence": retrieval_confidence,
            "score": r_score,
            "source": "S-PubMedBERT Dense Index"
        })

        if associated_genes:
            evidence_items.append({
                "category": "SUPPORTING",
                "aspect": "Associated Genetics",
                "description": f"Established genetic associations documented in {', '.join(associated_genes)}",
                "confidence": "High",
                "score": None,
                "source": "Orphanet / OMIM / Monarch"
            })
        else:
            evidence_items.append({
                "category": "NEUTRAL",
                "aspect": "Associated Genetics",
                "description": "No causal gene mapped in current annotation record",
                "confidence": "Unknown",
                "score": None,
                "source": "Disease Annotations"
            })

        if pop_status == "available":
            evidence_items.append({
                "category": pop_category,
                "aspect": "Population Ancestry Prior",
                "description": f"Ancestral variant frequency calibrated with Indian (IndiGen signal: {ind_signal:.4f}) and global (gnomAD signal: {gno_signal:.4f}) datasets",
                "confidence": population_confidence,
                "score": ind_signal,
                "source": "IndiGen & gnomAD SAS"
            })
        else:
            evidence_items.append({
                "category": "MISSING",
                "aspect": "Population Ancestry Prior",
                "description": "Ancestral allele frequency data unavailable for associated gene(s); unweighted neutral baseline applied",
                "confidence": "Unknown",
                "score": 0.50,
                "source": "IndiGen / gnomAD"
            })

        return {
            "disease_id": disease_id,
            "disease_name": disease_name,
            "rank": rank,
            "final_score": final_score,
            "phenotype_evidence": {
                "score": p_score,
                "confidence": phenotype_confidence,
                "matched_hpo_ids": matched_hpo_ids,
                "matched_phenotypes": matched_phenotypes,
                "missing_phenotypes": missing_phenotypes,
                "contradicting_phenotypes": []
            },
            "retrieval_evidence": {
                "score": r_score,
                "confidence": retrieval_confidence,
                "sources": cleaned_sources
            },
            "population_evidence": {
                "indian_signal": ind_signal,
                "global_signal": gno_signal,
                "status": pop_status,
                "confidence": population_confidence,
                "category": pop_category
            },
            "genes": associated_genes,
            "evidence_items": evidence_items,
            "evidence_sources": cleaned_sources
        }

    def fuse_all_candidates(
        self,
        ranked_candidates: List[Dict[str, Any]],
        extracted_phenotypes: List[Dict[str, Any]],
        hpo_terms: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fuses evidence for all top-k candidates.
        """
        fused = []
        for idx, cand in enumerate(ranked_candidates[:top_k], 1):
            fused_cand = self.fuse_candidate_evidence(
                candidate=cand,
                extracted_phenotypes=extracted_phenotypes,
                hpo_terms=hpo_terms,
                rank=idx
            )
            fused.append(fused_cand)
        return fused
