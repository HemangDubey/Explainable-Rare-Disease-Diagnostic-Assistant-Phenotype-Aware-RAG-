"""Efficient, provenance-carrying population lookup for genes / variants.

Everything is held in dictionaries built once from the on-disk gnomAD per-gene cache (and the IndiGen
parquet when it exists). Lookups never scan files per request.

States (never collapsed into numbers):
    available       real evidence found
    not_found       the source was queried / is present but has no usable record for this gene
    unavailable     the dataset is missing or this gene has not been ingested yet
    not_applicable  the disease has no associated gene
"""
import bisect
import json
import math
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.population.gnomad_adapter import DATASET, summarize_gene
from src.population.indigen_adapter import IndiGenStore
from src.population.population_schema import AVAILABLE, GENE_LEVEL, NOT_APPLICABLE, NOT_FOUND, UNAVAILABLE

MIN_REFERENCE_GENES = 100      # an empirical CDF over fewer genes is not a meaningful reference


def compare_frequencies(indian_af: Optional[float], global_af: Optional[float]) -> dict:
    """Safe Indian-vs-global comparison. Missing or 0/0 cases yield None, never a fake number."""
    out = {"indian_af": indian_af, "global_af": global_af, "difference": None, "ratio": None, "log2_ratio": None}
    if indian_af is None or global_af is None:
        return out
    out["difference"] = indian_af - global_af
    if global_af > 0 and indian_af > 0:
        out["ratio"] = indian_af / global_af
        out["log2_ratio"] = math.log2(out["ratio"])
    elif global_af > 0:                    # observed globally, not in the Indian dataset
        out["ratio"] = 0.0
    return out                              # global_af == 0: ratio undefined (None)


class _Ecdf:
    def __init__(self, values: List[float], min_n: int = MIN_REFERENCE_GENES):
        self.v = sorted(x for x in values if x > 0)
        self.min_n = min_n

    @property
    def n(self):
        return len(self.v)

    def __call__(self, x: float) -> Optional[float]:
        if self.n < self.min_n:
            return None                     # reference distribution too small -> no signal
        if x <= 0:
            return 0.0
        return bisect.bisect_right(self.v, x) / self.n


class _EcdfAll:
    """Empirical CDF over ALL reference values (including negatives); used for log2 ratios."""

    def __init__(self, values: List[float], min_n: int = MIN_REFERENCE_GENES):
        self.v = sorted(values)
        self.min_n = min_n

    @property
    def n(self):
        return len(self.v)

    def __call__(self, x: float) -> Optional[float]:
        if self.n < self.min_n:
            return None
        return bisect.bisect_right(self.v, x) / self.n


class PopulationLookup:
    def __init__(self, config_path="configs/config.yaml", cache_dir=None, min_reference_genes=None, indigen=None):
        cfg = yaml.safe_load(open(config_path, encoding="utf-8"))["population"]
        self.cfg = cfg
        self.min_n = int(min_reference_genes if min_reference_genes is not None else cfg.get("min_reference_genes", MIN_REFERENCE_GENES))
        self.cache_dir = Path(cache_dir or cfg["gnomad_gene_cache_dir"])
        self.indigen = indigen or IndiGenStore(config_path)
        self.genes: Dict[str, dict] = {}
        self.reload()

    def reload(self):
        self.genes = {}
        if self.cache_dir.exists():
            for p in self.cache_dir.glob("*.json"):
                rec = json.load(open(p, encoding="utf-8"))
                self.genes[rec["input_gene"].upper()] = {"rec": rec, "sum": summarize_gene(rec)}
        sums = [g["sum"] for g in self.genes.values() if g["sum"]["status"] == AVAILABLE and g["sum"].get("has_plp")]
        self.cdf_global = _Ecdf([s["caf_global"] for s in sums], self.min_n)
        self.cdf_sas = _Ecdf([s["caf_sas"] for s in sums], self.min_n)
        self.cdf_enrich = _EcdfAll([math.log2(s["caf_sas"] / s["caf_global"]) for s in sums
                                    if s["caf_sas"] > 0 and s["caf_global"] > 0], self.min_n)
        self.indigen_caf = {}
        if self.indigen.available:
            for sym, g in self.genes.items():
                af, found = 0.0, 0
                for v in g["rec"].get("plp_variants", []):
                    r = self.indigen.lookup_variant(v["variant_id"])
                    if r["status"] == AVAILABLE and r.get("allele_frequency") is not None:
                        af += r["allele_frequency"]; found += 1
                self.indigen_caf[sym] = (af, found)
        self.cdf_indigen = _Ecdf([a for a, f in self.indigen_caf.values() if f > 0], self.min_n)

    # ---- gene-level lookups ----------------------------------------------------------------
    def add_gene(self, rec: dict):
        """Register one newly ingested gene record without rebuilding the reference distributions (ECDFs). The gene's own
        evidence becomes available immediately; reference CDFs are refreshed at the next reload()/restart so signal values stay
        stable within a running process (population weight is 0, so ranking is unaffected either way)."""
        key = rec["input_gene"].upper()
        self.genes[key] = {"rec": rec, "sum": summarize_gene(rec)}
        if self.indigen.available:
            af, found = 0.0, 0
            for v in rec.get("plp_variants", []):
                r = self.indigen.lookup_variant(v["variant_id"])
                if r["status"] == AVAILABLE and r.get("allele_frequency") is not None:
                    af += r["allele_frequency"]; found += 1
            self.indigen_caf[key] = (af, found)

    def lookup_gene(self, symbol: str) -> dict:
        key = str(symbol).strip().upper()
        g = self.genes.get(key)
        out = {"input_gene": symbol, "level": GENE_LEVEL}
        if g is None:
            out.update(normalized_gene=None, mapping_source=None, mapping_status="unresolved",
                       gnomad={"source": "gnomAD", "status": UNAVAILABLE, "reason": "gene not ingested"},
                       indigen={"source": "IndiGen", "status": UNAVAILABLE})
            if not self.indigen.available:
                out["indigen"]["reason"] = "IndiGen dataset not available (access required)"
            return out
        s = g["sum"]
        if s["status"] != AVAILABLE:
            out.update(normalized_gene=None, mapping_source="gnomAD/GENCODE gene lookup", mapping_status="not_found",
                       gnomad={"source": "gnomAD", "status": NOT_FOUND, "reason": "gene symbol not recognised"})
        else:
            changed = s["normalized_gene"].upper() != key
            out.update(normalized_gene=s["normalized_gene"], mapping_source="gnomAD/GENCODE gene lookup",
                       mapping_status="alias_resolved" if changed else "mapped")
            if not s["has_plp"]:
                out["gnomad"] = {"source": "gnomAD", "status": NOT_FOUND, "dataset_version": s["dataset_version"],
                                 "reason": "no ClinVar pathogenic/likely-pathogenic variants for this gene"}
            else:
                out["gnomad"] = {"source": "gnomAD", "status": AVAILABLE, "dataset_version": s["dataset_version"],
                                 "statistic": "cumulative allele frequency of ClinVar P/LP variants (gnomAD global / gnomAD South Asian)",
                                 "caf_global": s["caf_global"], "caf_sas": s["caf_sas"],
                                 "n_plp_variants": s["n_plp_with_counts"], "clinvar_plp_total": s["clinvar_plp"]}
        if self.indigen.available and key in self.indigen_caf:
            af, found = self.indigen_caf[key]
            out["indigen"] = ({"source": "IndiGen", "status": AVAILABLE, "dataset_version": self.indigen.version,
                               "caf": af, "n_variants_found": found} if found
                              else {"source": "IndiGen", "status": NOT_FOUND, "dataset_version": self.indigen.version})
        else:
            out["indigen"] = {"source": "IndiGen", "status": UNAVAILABLE,
                              "reason": "IndiGen dataset not available (access required)" if not self.indigen.available else "gene not ingested"}
        return out

    def coverage_summary(self, all_genes: List[str]) -> dict:
        uniq = sorted(set(all_genes))
        st = [self.lookup_gene(g) for g in uniq]
        return {
            "total_genes": len(uniq),
            "gnomad_available": sum(s["gnomad"]["status"] == AVAILABLE for s in st),
            "gnomad_not_found": sum(s["gnomad"]["status"] == NOT_FOUND for s in st),
            "gnomad_unavailable_or_not_ingested": sum(s["gnomad"]["status"] == UNAVAILABLE for s in st),
            "indigen_available": sum(s["indigen"]["status"] == AVAILABLE for s in st),
            "indigen_status": "available" if self.indigen.available else "unavailable - access required",
            "reference_genes_enrichment": self.cdf_enrich.n,
            "reference_genes_global": self.cdf_global.n, "reference_min_required": self.min_n,
            "signal_defined": self.cdf_global.n >= self.min_n,
        }
