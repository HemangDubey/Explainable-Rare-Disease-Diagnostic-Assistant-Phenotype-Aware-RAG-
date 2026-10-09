import re
import uuid
import logging
from typing import Dict, Any, List, Optional
from src.knowledge.hpo_normalizer import HPONormalizer
from src.scribe.schemas import StructuredClinicalCase, ScribeResponse

logger = logging.getLogger("clinical_scribe")

class ClinicalScribeEngine:
    def __init__(self, config_path="configs/config.yaml"):
        self.normalizer = HPONormalizer(config_path=config_path)

    def extract_structured_case(self, clinical_text: str, case_id: Optional[str] = None) -> ScribeResponse:
        cid = case_id or str(uuid.uuid4())[:8]
        text_clean = clinical_text.strip()

        # 1. Detect negated statements and relevant negatives
        negation_patterns = [
            r'no\s+(?:known\s+)?family\s+history[^\.\,;]*',
            r'no\s+(?:known\s+)?(?:seizures|hypotonia|dysmorphism|cardiac|neurological|history)[^\.\,;]*',
            r'denies\s+[^\.\,;]+',
            r'without\s+[^\.\,;]+'
        ]
        
        relevant_negatives = []
        for pat in negation_patterns:
            matches = re.findall(pat, text_clean, re.IGNORECASE)
            for m in matches:
                relevant_negatives.append(m.strip())

        # 2. Extract phenotype mentions (positive mentions only)
        # Remove common introductory prefixes for candidate extraction
        trimmed = re.sub(r'^(?:patient|child|infant)\s+(?:presents\s+with|is\s+a|has)\s+', '', text_clean, flags=re.IGNORECASE)
        sentences = re.split(r'[\.\;\n]', trimmed)
        
        positive_phrases = []
        for s in sentences:
            s_str = s.strip()
            if not s_str:
                continue
            # Skip if sentence is purely negative
            if re.search(r'^(?:no\s|denies\s|without\s)', s_str, re.IGNORECASE):
                continue
            # Split clauses by comma / 'and' / 'with'
            clauses = re.split(r'[,&]|\band\b|\bwith\b', s_str)
            for cl in clauses:
                cl_clean = cl.strip()
                if cl_clean and len(cl_clean) > 2 and not re.search(r'^(?:no\s|denies\s)', cl_clean, re.IGNORECASE):
                    positive_phrases.append(cl_clean)

        # Normalize positive phenotype mentions to HPO terms
        hpo_terms = []
        extracted_phenotypes = []
        seen_hpo_ids = set()

        for phrase in positive_phrases:
            norms = self.normalizer.normalize(phrase, top_k=1)
            if norms:
                best = norms[0]
                h_id = best["hpo_id"]
                if h_id not in seen_hpo_ids:
                    seen_hpo_ids.add(h_id)
                    hpo_terms.append(best)
                    extracted_phenotypes.append({
                        "phenotype": best["name"],
                        "hpo_id": h_id,
                        "match_score": best.get("score", 1.0),
                        "source_span": phrase
                    })

        # 3. Extract demographic / clinical metadata without hallucinating
        age_match = re.search(r'(\d+[\-\s]year[\-\s]old|\d+[\-\s]month[\-\s]old|infant|child|adult)', text_clean, re.IGNORECASE)
        age = age_match.group(1) if age_match else None

        dev_match = re.search(r'(developmental\s+delay[^\.\,;]*|infancy|milestone[^\.\,;]*)', text_clean, re.IGNORECASE)
        dev_history = dev_match.group(1).strip() if dev_match else None

        fam_match = re.search(r'((?:no\s+known\s+)?family\s+history[^\.\,;]*)', text_clean, re.IGNORECASE)
        fam_history = fam_match.group(1).strip() if fam_match else None

        onset_match = re.search(r'(since\s+birth|since\s+infancy|early\s+onset|acute\s+onset|\d+\s+(?:months|years)\s+ago)', text_clean, re.IGNORECASE)
        onset = onset_match.group(1).strip() if onset_match else None

        # Chief complaint determination
        chief_complaint = None
        if positive_phrases:
            chief_complaint = positive_phrases[0]

        # 4. Check for unstated/missing fields
        missing_information = []
        if not age:
            missing_information.append("Patient exact age")
        if not fam_history:
            missing_information.append("Family history details")
        if not dev_history:
            missing_information.append("Developmental history timeline")
        if not onset:
            missing_information.append("Onset timing and progression details")
        missing_information.append("Specific genetic variant coordinates / NGS panel results")
        missing_information.append("Laboratory metabolic profiling")

        # Build Structured Clinical Case
        phenotype_names = [ep["phenotype"] for ep in extracted_phenotypes]
        
        structured_case = StructuredClinicalCase(
            case_id=cid,
            age=age,
            chief_complaint=chief_complaint,
            symptoms=positive_phrases,
            phenotypes=phenotype_names,
            onset=onset,
            duration=None,
            progression=None,
            family_history=fam_history,
            developmental_history=dev_history,
            relevant_negatives=relevant_negatives,
            medications=[],
            investigations=[],
            genetic_findings=None,
            notes=None,
            extracted_hpo_terms=hpo_terms,
            confidence={},
            source_text=clinical_text
        )

        return ScribeResponse(
            case_id=cid,
            structured_case=structured_case,
            phenotypes=extracted_phenotypes,
            hpo_terms=hpo_terms,
            missing_information=missing_information,
            confidence={}   # no calibrated confidence exists; the previous hard-coded values were removed
        )
