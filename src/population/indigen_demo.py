"""IndiGen DEMO data provider: synthetic values for demonstrating the IndiGen UI. NOT IndiGen evidence.

Isolation rules (enforced by tests/test_indigen_demo.py):
  * this module is never imported by the ranking, the population lookup or the pipeline; only the gene-evidence service (display),
    the genomic API and the report appendix use it;
  * demo values are returned under their own key (`indigen_demo`) and label, never in the real `indigen` field;
  * when an authorised real IndiGen export has been ingested, demo values are not shown (status "superseded_by_real_data");
  * demo mode is opt-in per request and can be disabled server-wide (INDIGEN_DEMO_ALLOWED=0; off by default when APP_ENV=production).
"""
import gzip
import json
import os
from pathlib import Path
from typing import Dict, Optional

DEMO_LABEL = "IndiGen Demo — Synthetic Data, Not Official IndiGen Evidence"
SHORT_LABEL = "IndiGen Demo (synthetic)"
SCHEMA_VERSION = "indigen-demo/1"
DEMO_PATH = Path("data/demo/indigen_demo/indigen_demo_v1.json.gz")


def demo_allowed() -> bool:
    v = os.environ.get("INDIGEN_DEMO_ALLOWED")
    if v is not None:
        return v.strip().lower() in ("1", "true", "yes", "on")
    return os.environ.get("APP_ENV", "development").lower() != "production"


class IndiGenDemoProvider:
    def __init__(self, path: Path = DEMO_PATH):
        self.path = Path(path)
        self.data: Optional[Dict] = None
        self.error: Optional[str] = None
        if self.path.exists():
            try:
                with gzip.open(self.path, "rt", encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("schema_version") != SCHEMA_VERSION or not (d.get("provenance") or {}).get("synthetic"):
                    raise ValueError("not a synthetic IndiGen demo file of the expected schema")
                self.data = d
            except Exception as e:  # noqa: BLE001 - reported as status, the rest of the app keeps working
                self.error = f"{type(e).__name__}: {e}"

    @property
    def available(self) -> bool:
        return self.data is not None

    @property
    def provenance(self) -> dict:
        return dict((self.data or {}).get("provenance") or {}, label=DEMO_LABEL, synthetic=True)

    def status(self) -> dict:
        if self.available:
            return {"status": "available", "label": DEMO_LABEL, "n_genes": self.data["n_genes"], "n_records": self.data["n_records"],
                    "provenance": self.provenance}
        return {"status": "error" if self.error else "unavailable", "label": DEMO_LABEL,
                "reason": self.error or f"demo dataset not built (run: python scripts/build_indigen_demo.py -> {self.path})"}

    def gene(self, symbol: str) -> dict:
        base = {"label": DEMO_LABEL, "short_label": SHORT_LABEL, "synthetic": True, "source": "IndiGen demo provider (synthetic)"}
        if not self.available:
            return {**base, **self.status()}
        g = self.data["genes"].get(str(symbol).upper())
        if g is None:
            return {**base, "status": "not_found", "reason": "no demo records were generated for this gene (rebuild with --genes)"}
        return {**base, "status": "available", "cumulative_af": g["demo_caf"], "n_variants": g["n_variants"],
                "n_variants_nonzero": g["n_variants_nonzero"], "simulated_allele_number": self.data["provenance"]["simulated_allele_number"],
                "variants": g["variants"], "provenance": self.provenance}
