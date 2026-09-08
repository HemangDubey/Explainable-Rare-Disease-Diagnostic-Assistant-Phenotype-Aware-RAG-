from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class CounterfactualRequest(BaseModel):
    case_id: Optional[str] = Field(default=None, description="Active case ID. Auto-retrieved from session if omitted.")
    clinical_text: Optional[str] = Field(default=None, description="Optional raw text input if running on new case text.")
    operation: str = Field(..., example="remove", description="Operation type: 'remove', 'add', 'toggle', 'compare'")
    phenotype_id: Optional[str] = Field(default=None, example="HP:0001250", description="HPO ID or label to target for add/remove/toggle.")
    added_phenotypes: Optional[List[str]] = Field(default_factory=list, description="List of HPO IDs or phenotype terms to add.")
    removed_phenotypes: Optional[List[str]] = Field(default_factory=list, description="List of HPO IDs or phenotype terms to remove.")
    modified_phenotypes: Optional[List[str]] = Field(default_factory=list, description="Exact target phenotype list for custom state comparison.")
    exp_config: Optional[str] = Field(default="rag_indigen_gnomad", description="Population ranking experiment configuration.")
    top_k: Optional[int] = Field(default=5, description="Top K candidate diseases to compare.")

class CandidateRankDelta(BaseModel):
    disease_id: str
    disease_name: str
    original_rank: int
    counterfactual_rank: int
    original_score: float
    counterfactual_score: float
    score_delta: float
    rank_change: int  # e.g., +2 (moved up), -2 (moved down), 0 (unchanged)
    trend: str        # "up", "down", "unchanged"

class PhenotypeImpactItem(BaseModel):
    hpo_id: str
    hpo_name: str
    impact_score: float         # mean absolute or specific disease score delta
    sensitivity_level: str      # "High ranking sensitivity", "Moderate ranking sensitivity", "Low ranking sensitivity"
    affected_candidates_count: int

class CounterfactualExperimentRecord(BaseModel):
    experiment_id: str
    case_id: str
    operation: str
    timestamp: str
    baseline_phenotypes: List[Dict[str, Any]]
    modified_phenotypes: List[Dict[str, Any]]
    ranking_deltas: List[CandidateRankDelta]

class CounterfactualResponse(BaseModel):
    experiment_id: str
    case_id: str
    operation: str
    baseline_phenotypes: List[Dict[str, Any]]
    modified_phenotypes: List[Dict[str, Any]]
    baseline_ranking: List[Dict[str, Any]]
    counterfactual_ranking: List[Dict[str, Any]]
    ranking_deltas: List[CandidateRankDelta]
    phenotype_impacts: List[PhenotypeImpactItem]
    insights: List[str]
    disclaimer: str = "Counterfactual analysis shows how candidate disease prioritization changes when selected phenotype information is modified. This is a computational sensitivity analysis and does not establish clinical causality."
