from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ScribeRequest(BaseModel):
    case_id: Optional[str] = Field(default=None, description="Optional case identifier. Auto-generated if not provided.")
    clinical_text: str = Field(..., description="Unstructured clinical narrative text.", example="Patient is a 7-year-old child with developmental delay since infancy, hypotonia, short stature and recurrent seizures. No known family history.")

class StructuredClinicalCase(BaseModel):
    case_id: str
    age: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    phenotypes: List[str] = Field(default_factory=list)
    onset: Optional[str] = None
    duration: Optional[str] = None
    progression: Optional[str] = None
    family_history: Optional[str] = None
    developmental_history: Optional[str] = None
    relevant_negatives: List[str] = Field(default_factory=list)
    medications: List[str] = Field(default_factory=list)
    investigations: List[str] = Field(default_factory=list)
    genetic_findings: Optional[str] = None
    notes: Optional[str] = None
    extracted_hpo_terms: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Dict[str, float] = Field(default_factory=dict)
    source_text: str

class ScribeResponse(BaseModel):
    case_id: str
    structured_case: StructuredClinicalCase
    phenotypes: List[Dict[str, Any]]
    hpo_terms: List[Dict[str, Any]]
    missing_information: List[str]
    confidence: Dict[str, float]
    disclaimer: str = "Extracted case structure and HPO annotations are clinical decision support aids and require professional verification."
