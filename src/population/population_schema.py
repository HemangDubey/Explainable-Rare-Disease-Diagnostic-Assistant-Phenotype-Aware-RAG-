"""Canonical population-evidence schema. Only fields a source actually provides are populated."""
from dataclasses import asdict, dataclass, field
from typing import Optional

# Evidence states (never collapsed into 0 / 0.5 / 1)
AVAILABLE = "available"
NOT_FOUND = "not_found"
UNAVAILABLE = "unavailable"          # dataset could not be accessed / not installed
NOT_APPLICABLE = "not_applicable"    # e.g. disease has no associated gene

# Evidence level
VARIANT_LEVEL = "VARIANT_LEVEL"
GENE_LEVEL = "GENE_LEVEL"


@dataclass
class VariantFrequency:
    variant_id: str                      # canonical chr:pos:ref:alt (GRCh38)
    chromosome: str
    position: int
    ref: str
    alt: str
    source: str                          # "IndiGen" | "gnomAD"
    dataset_version: str
    population: str                      # e.g. "global", "sas"
    status: str = AVAILABLE
    gene: Optional[str] = None
    allele_frequency: Optional[float] = None
    allele_count: Optional[int] = None
    allele_number: Optional[int] = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class GeneEvidence:
    """Gene-level population statistic (explicitly NOT variant-level)."""
    source: str
    status: str
    level: str = GENE_LEVEL
    gene: Optional[str] = None
    statistic: Optional[str] = None      # human-readable definition of the number below
    value: Optional[float] = None
    n_variants: Optional[int] = None
    dataset_version: Optional[str] = None
    detail: dict = field(default_factory=dict)

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v not in (None, {})}
