"""Validated models for the Phase 5R clinical-note draft."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DRAFT_STATUS_LABEL = "Draft — clinician review required"

SECTION_ORDER = ["presenting_concerns", "history_of_present_illness", "reported_symptoms_and_phenotypes", "relevant_medical_history",
                 "family_history", "examination_findings", "investigations_and_results", "known_diagnoses",
                 "missing_or_unverified_information", "clinician_review_notes"]
SECTION_TITLES = {
    "presenting_concerns": "Presenting concerns", "history_of_present_illness": "History of present illness",
    "reported_symptoms_and_phenotypes": "Reported symptoms and phenotypes", "relevant_medical_history": "Relevant medical history",
    "family_history": "Relevant family history", "examination_findings": "Examination findings",
    "investigations_and_results": "Investigations and results", "known_diagnoses": "Known diagnoses",
    "missing_or_unverified_information": "Missing or unverified information", "clinician_review_notes": "Clinician review notes",
}


class SourceSpan(BaseModel):
    start: int
    end: int
    input: Literal["clinical_note", "clinician_phenotype_list", "system"] = "clinical_note"


class DraftStatement(BaseModel):
    id: str
    text: str
    source: SourceSpan
    origin: Literal["source", "clinician_supplied", "system", "clinician_edit"] = "source"
    subject: Literal["patient", "relative"] = "patient"
    relationship: Optional[str] = None
    reporting: Literal["reported", "observed", "unspecified"] = "unspecified"
    contains_negation_cue: bool = False
    contains_uncertainty_cue: bool = False
    pending: bool = False
    temporal: List[str] = Field(default_factory=list)
    n_mentions: int = 0
    verified: bool = False
    edited: bool = False
    removed: bool = False


class DraftPhenotype(BaseModel):
    id: str
    statement_id: str
    mention: str
    status: Literal["present", "negated", "uncertain", "relative_finding"]
    subject: Literal["patient", "relative"] = "patient"
    relationship: Optional[str] = None
    hpo_id: Optional[str] = None
    hpo_name: Optional[str] = None
    normalization_status: str = "not_attempted"
    mapping_score: Optional[float] = None
    candidates: List[Any] = Field(default_factory=list)
    source: SourceSpan
    temporal: List[str] = Field(default_factory=list)
    verified: bool = False


class DraftSection(BaseModel):
    title: str
    status: Literal["provided", "not_provided"]
    items: List[DraftStatement] = Field(default_factory=list)


class Draft(BaseModel):
    draft_id: str
    status: str = DRAFT_STATUS_LABEL
    review_state: Literal["draft", "reviewed"] = "draft"   # never 'signed'/'approved'/'final'
    created_at: str
    updated_at: Optional[str] = None
    generated_by: str
    provider: Dict[str, Any] = Field(default_factory=dict)
    source_text: str
    statements: List[DraftStatement]
    sections: Dict[str, DraftSection]
    phenotypes: List[DraftPhenotype]
    diagnosis_input: str = ""
    diagnosis_input_excluded: Dict[str, int] = Field(default_factory=dict)
    input_check: Dict[str, Any] = Field(default_factory=dict)
    clinician_notes: str = ""
    saved: bool = False
    disclaimer: str = ("Documentation draft generated from the supplied note only. It is not a diagnosis, has not been reviewed, and "
                       "unmentioned items are 'not provided' — not 'absent'.")


class DraftUpdate(BaseModel):
    """Clinician edits. Statement edits replace text (marked edited); removals are soft; verified flags are per item."""
    statements: Optional[List[Dict[str, Any]]] = None      # [{id, text?, verified?, removed?}]
    phenotypes: Optional[List[Dict[str, Any]]] = None      # [{id, verified?, status?}]
    clinician_notes: Optional[str] = None
    review_state: Optional[Literal["draft", "reviewed"]] = None
