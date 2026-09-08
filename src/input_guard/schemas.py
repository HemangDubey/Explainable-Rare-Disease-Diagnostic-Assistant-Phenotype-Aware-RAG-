from pydantic import BaseModel, Field
from typing import List, Optional

class ValidationRequest(BaseModel):
    text: str = Field(..., example="Patient presents with hypotonia and developmental delay.")

class ValidationResponse(BaseModel):
    status: str = Field(..., example="VALID_CLINICAL") # VALID_CLINICAL, NEEDS_ENHANCEMENT, INSUFFICIENT, NON_CLINICAL, INAPPROPRIATE
    clinical_relevance: str = Field(..., example="HIGH") # HIGH, MODERATE, LOW, NONE
    reason: str = Field(..., example="Valid clinical presentation detected.")
    suggested_action: str = Field(..., example="Ready for diagnostic analysis.")
    is_valid_clinical: bool = Field(default=True)

class EnhanceRequest(BaseModel):
    text: str = Field(..., example="pt has dev delay and seizures since 2 yrs")

class EnhanceResponse(BaseModel):
    status: str = Field(..., example="NEEDS_ENHANCEMENT") # VALID_CLINICAL, NEEDS_ENHANCEMENT, NON_CLINICAL, INAPPROPRIATE, INSUFFICIENT, ENHANCEMENT_UNAVAILABLE
    original_text: str
    enhanced_text: Optional[str] = Field(default=None)
    changes: List[str] = Field(default_factory=list)
    added_facts: List[str] = Field(default_factory=list)
    removed_facts: List[str] = Field(default_factory=list)
    reason: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None)
