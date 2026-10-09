"""Gene-level reference evidence service: ONE backend source for every genomic evidence view (Digital Twin panel, gene API).

Per gene it combines
  * ClinVar  - every P/LP GRCh38 germline record (>=1 review star) for the gene, read from the processed ClinVar parquet. Independent of
               gnomAD: ClinVar evidence is shown even when gnomAD counts have not been fetched.
  * gnomAD   - v4.1 exome AC/AN (global) and AC_sas/AN_sas (South Asian ancestry group) for those variants, from the per-gene cache.
               A gene missing from the cache is "not_ingested" (fetchable on demand from the official public VCFs), not "unavailable".
  * IndiGen  - only from an authorised export ingested by src/population/indigen_adapter.py; otherwise "unavailable". Never substituted.

States are explicit and distinct:
  available     evidence present
  not_found     the source has no record for this gene (a real empty result, e.g. no P/LP variants in ClinVar)
  not_ingested  gnomAD counts not fetched yet for this gene (fetch with ingest())
  error         the last fetch failed (network/parse); retryable, never cached as empty
  unavailable   the dataset itself is missing (IndiGen without access)

Reference variants are never patient variants: `patient_variant` is always "not_provided" here, because no case workflow accepts a
patient genotype.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from src.population import gnomad_bulk
from src.population.gnomad_adapter import summarize_gene
from src.population.indigen_demo import DEMO_LABEL, SHORT_LABEL, IndiGenDemoProvider, demo_allowed

CLINVAR_URL = "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/"
MAX_VARIANTS_SHOWN = 25
_MAX_CONCURRENT_FETCHES = 2


def _atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


class GeneEvidenceService:
    def __init__(self, lookup, plp_path="data/processed/population/clinvar_plp_grch38.parquet",
                 totals_path="data/processed/population/clinvar_gene_totals.json",
                 provenance_path="data/processed/population/clinvar_provenance.json",
                 symbol_index_path="data/processed/population/gene_symbol_index.json",
                 cache_dir=None, fetch: Optional[Callable] = None, demo_provider=None):
        self.lookup = lookup
        self.cache_dir = Path(cache_dir or lookup.cache_dir)
        self.plp = pd.read_parquet(plp_path)
        self._rows = self.plp.groupby("gene").indices                       # gene -> row positions
        self.totals: Dict[str, int] = json.load(open(totals_path, encoding="utf-8"))
        self.clinvar_prov = json.load(open(provenance_path, encoding="utf-8")) if Path(provenance_path).exists() else {}
        ix = json.load(open(symbol_index_path, encoding="utf-8")) if Path(symbol_index_path).exists() else {}
        self._by_gene_id = ix.get("clinvar_by_gene_id", {})
        self._kb_gene_id = ix.get("hpo_symbol_to_gene_id", {})
        self._upper = {s.upper(): s for s in self.totals}
        self._fetch = fetch or gnomad_bulk.fetch_gene
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._slots = threading.BoundedSemaphore(_MAX_CONCURRENT_FETCHES)
        self.errors: Dict[str, dict] = {}                                  # last fetch failure per gene (retryable)
        self._demo = demo_provider                                         # synthetic IndiGen demo (display only)

    # ---- symbol resolution ----------------------------------------------------------------------------------------------
    def resolve(self, symbol: str) -> dict:
        raw = str(symbol or "").strip()
        key = raw.upper()
        if key in self._upper:
            sym = self._upper[key]
            return {"input": raw, "symbol": sym, "status": "mapped" if sym == raw else "case_normalised", "via": "ClinVar gene symbol"}
        gid = self._kb_gene_id.get(key)
        cv = self._by_gene_id.get(gid) if gid else None
        if cv and cv in self.totals:
            return {"input": raw, "symbol": cv, "status": "alias_resolved", "via": f"NCBI GeneID {gid} (HPO phenotype_to_genes -> ClinVar)"}
        return {"input": raw, "symbol": key or None, "status": "not_found",
                "via": f"NCBI GeneID {gid}" if gid else None,
                "reason": "no GRCh38 ClinVar record for this gene symbol" + (f" or its NCBI GeneID {gid}" if gid else "")}

    # ---- ClinVar ---------------------------------------------------------------------------------------------------------
    def clinvar_records(self, sym: str) -> List[dict]:
        pos = self._rows.get(sym)
        if pos is None:
            return []
        out = []
        for r in self.plp.iloc[pos].drop_duplicates("variant_id").to_dict("records"):
            c, p, ref, alt = r["variant_id"].split(":")
            out.append({"variant_id": r["variant_id"], "chrom": c, "pos": int(p), "ref": ref, "alt": alt, "build": "GRCh38",
                        "clinvar_variation_id": str(r["variation_id"]), "clinvar_url": CLINVAR_URL.format(r["variation_id"]),
                        "clinical_significance": r["clinical_significance"], "review_status": r["review_status"],
                        "gold_stars": int(r["gold_stars"]), "variant_type": r.get("Type")})
        return out

    # ---- gnomAD cache ----------------------------------------------------------------------------------------------------
    def cached_record(self, sym: str) -> Optional[dict]:
        g = self.lookup.genes.get(sym.upper())
        if g is not None:
            return g["rec"]
        path = self.cache_dir / f"{sym}.json"                              # written by the CLI while the server was running
        if path.exists():
            rec = json.load(open(path, encoding="utf-8"))
            self.lookup.add_gene(rec)
            return rec
        return None

    def gnomad_state(self, sym: str) -> dict:
        rec = self.cached_record(sym)
        if rec is not None:
            return {"status": rec.get("status"), "record": rec}
        if sym in self.errors:
            return {"status": "error", **self.errors[sym]}
        return {"status": "not_ingested", "reason": "gnomAD v4.1 exome counts for this gene have not been fetched yet"}

    def ingest(self, symbol: str, force: bool = False) -> dict:
        """Fetch real gnomAD v4.1 exome counts for one gene from the official public VCFs (HTTP range reads) and cache them.
        Idempotent: an existing cache entry is reused unless force=True. Failures are recorded as retryable errors, never cached."""
        res = self.resolve(symbol)
        if res["status"] == "not_found":
            return {"gene": res["symbol"], "status": "not_found", "resolution": res}
        sym = res["symbol"]
        with self._locks_guard:
            lock = self._locks.setdefault(sym, threading.Lock())
        with lock:                                                         # one fetch per gene at a time; later callers reuse it
            if not force and self.cached_record(sym) is not None:
                return {"gene": sym, "status": "cached", "resolution": res}
            if not self._slots.acquire(timeout=120):
                return {"gene": sym, "status": "busy", "reason": "too many concurrent gnomAD fetches; retry shortly"}
            try:
                pos = self._rows.get(sym)
                sub = self.plp.iloc[pos] if pos is not None else self.plp.iloc[0:0]
                rec = self._fetch(sym, sub, self.totals.get(sym, 0), sym in self.totals)
            except Exception as e:  # noqa: BLE001 - reported to the caller as a retryable error
                rec = {"status": "error", "reason": f"{type(e).__name__}: {e}"}
            finally:
                self._slots.release()
            if rec.get("status") == "error":
                self.errors[sym] = {"reason": rec.get("reason", "fetch failed"), "at": datetime.now(timezone.utc).isoformat()}
                return {"gene": sym, "status": "error", "reason": self.errors[sym]["reason"], "resolution": res}
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.cache_dir / f"{sym}.json", rec)
            self.errors.pop(sym, None)
            self.lookup.add_gene(rec)
            return {"gene": sym, "status": "ingested", "resolution": res, "fetched_at": rec.get("fetched_at")}

    # ---- the single evidence contract ------------------------------------------------------------------------------------
    def evidence(self, symbol: str, indigen_demo: bool = False) -> dict:
        """The real evidence contract; with indigen_demo=True a separately labelled synthetic `indigen_demo` block is added for display.
        Real fields (clinvar, gnomad_*, indigen, population_comparison columns) are identical with and without the demo flag."""
        out = self._real_evidence(symbol)
        return self._attach_demo(out) if indigen_demo else out

    @property
    def demo(self):
        if self._demo is None:
            self._demo = IndiGenDemoProvider()
        return self._demo

    def _attach_demo(self, out: dict) -> dict:
        base = {"label": DEMO_LABEL, "short_label": SHORT_LABEL, "synthetic": True}
        if out["indigen"].get("status") == "available":
            out["indigen_demo"] = {**base, "status": "superseded_by_real_data",
                                   "reason": "authorised IndiGen data is loaded; demo values are not shown"}
            return out
        if not demo_allowed():
            out["indigen_demo"] = {**base, "status": "disabled", "reason": "IndiGen demo mode is disabled on this server (INDIGEN_DEMO_ALLOWED=0)"}
            return out
        d = self.demo.gene(out["gene"])
        out["indigen_demo"] = d
        if d.get("status") == "available":
            by = {v["variant_id"]: v for v in d["variants"]}
            pc = out["population_comparison"]
            pc["demo_column"] = {"label": SHORT_LABEL, "status": "available", "cumulative_af": d["cumulative_af"], "synthetic": True}
            for v in pc["variants"]:
                dv = by.get(v["variant_id"])
                v["af_indigen_demo"] = dv["demo_af"] if dv else None
        return out

    def _real_evidence(self, symbol: str) -> dict:
        from src.twin.builder import _gene_evidence                       # shared assembly (also used by older call sites)
        res = self.resolve(symbol)
        sym = res["symbol"] or str(symbol)
        if res["status"] == "not_found":
            out = _gene_evidence(sym, None, None)
            out["clinvar"] = {"status": "not_found", "reason": res["reason"]}
            for k in ("gnomad_global", "gnomad_south_asian"):
                out[k] = {"status": "not_found", "reason": "no ClinVar P/LP variants to look up in gnomAD for this gene"}
            from src.twin.builder import population_comparison
            out["population_comparison"] = population_comparison(out)
            out["resolution"] = res
            return out
        st = self.gnomad_state(sym)
        rec = st.get("record")
        records = self.clinvar_records(sym)
        if not records and rec is None:                                   # nothing to look up: an empty result, not a pending fetch
            st = {"status": "not_found", "reason": "no ClinVar P/LP (>=1 star) variants for this gene, so there is nothing to look up in gnomAD"}
        out = _gene_evidence(sym, (lambda s: rec) if rec else None, self.lookup.lookup_gene if rec else None,
                             clinvar_records=records, clinvar_meta=self._clinvar_meta(sym), gnomad_state=st)
        out["resolution"] = res
        return out

    def _clinvar_meta(self, sym: str) -> dict:
        p = self.clinvar_prov
        return {"source": "ClinVar variant_summary.txt.gz (NCBI)", "file_last_modified": p.get("file_last_modified_utc"),
                "processed_at": p.get("processed_at"), "reference_genome": "GRCh38",
                "filters": "germline; Pathogenic / Likely pathogenic / Pathogenic/Likely pathogenic; >=1 review star",
                "clinvar_total_variants": self.totals.get(sym)}
