"""Real gnomAD access through the public gnomAD GraphQL API (https://gnomad.broadinstitute.org/api).

Per gene we (1) list its ClinVar variants, (2) keep Pathogenic / Likely-pathogenic ones with review stars
>= min_gold_stars that are present in gnomAD, and (3) request their REAL gnomAD v4 allele counts
(exome + genome, including the South-Asian "sas" ancestry group) in small batches.
Results are cached on disk per gene (resumable, and avoids repeat requests).

Nothing here is synthetic. Missing data is recorded as a status, never as a number.
"""
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from src.population.population_schema import AVAILABLE, NOT_FOUND, UNAVAILABLE
from src.population.variant_normalizer import parse_variant_id

API_URL = "https://gnomad.broadinstitute.org/api"
DATASET = "gnomad_r4"                       # gnomAD v4 as exposed by the API
REFERENCE = "GRCh38"
_SAFE_ID = re.compile(r"^[0-9XYM]+-\d+-[ACGT]+-[ACGT]+$")
PLP = ("pathogenic", "likely pathogenic", "pathogenic/likely pathogenic")


class GnomadClient:
    def __init__(self, min_interval=6.5, timeout=120, retries=6, rate_limit_wait=150):
        self.min_interval, self.timeout, self.retries, self.rate_limit_wait = min_interval, timeout, retries, rate_limit_wait
        self._lock = threading.Lock()
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "rare-disease-assistant-research/1.0 (academic prototype)"

    def query(self, query: str, variables: Optional[dict] = None) -> dict:
        last_err = None
        for attempt in range(self.retries):
            with self._lock:
                wait = self.min_interval - (time.time() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.time()
            try:
                r = self.session.post(API_URL, json={"query": query, "variables": variables or {}}, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                last_err = f"HTTP {r.status_code}"
                if "rate limit" in r.text.lower():       # documented server-side throttle: wait it out, do not hammer
                    last_err = "rate limited"
                    time.sleep(self.rate_limit_wait)
                    continue
            except requests.RequestException as e:
                last_err = type(e).__name__
            time.sleep(2 ** attempt)
        raise ConnectionError(f"gnomAD API request failed: {last_err}")


_GENE_Q = """query($g:String!){ gene(gene_symbol:$g, reference_genome:GRCh38){
  gene_id symbol chrom clinvar_variants{ variant_id clinical_significance gold_stars in_gnomad } } }"""
_POP = "ac an populations{id ac an}"


def _batch_query(ids: List[str]) -> str:
    parts = []
    for i, vid in enumerate(ids):
        assert _SAFE_ID.match(vid), vid
        parts.append(f'v{i}: variant(variantId:"{vid}", dataset:{DATASET}){{ variant_id exome{{{_POP}}} genome{{{_POP}}} }}')
    return "query{ " + " ".join(parts) + " }"


def _counts(block: Optional[dict]):
    """-> (ac, an, sas_ac, sas_an) for an exome/genome block, or None if the variant is absent there."""
    if not block:
        return None
    sas = next((p for p in (block.get("populations") or []) if p["id"] == "sas"), None)
    return {"ac": block["ac"], "an": block["an"], "sas_ac": sas["ac"] if sas else None, "sas_an": sas["an"] if sas else None}


def is_plp(significance: Optional[str]) -> bool:
    s = (significance or "").strip().lower()
    return s in PLP


def fetch_gene(client: GnomadClient, symbol: str, min_gold_stars=1, batch=25) -> dict:
    rec = {"input_gene": symbol, "dataset": DATASET, "reference_genome": REFERENCE,
           "fetched_at": datetime.now(timezone.utc).isoformat(), "min_gold_stars": min_gold_stars}
    data = client.query(_GENE_Q, {"g": symbol})
    gene = (data.get("data") or {}).get("gene")
    if not gene:
        rec.update(status=NOT_FOUND, reason="gene symbol not found in gnomAD/GENCODE", plp_variants=[])
        return rec
    cv = gene.get("clinvar_variants") or []
    plp = [v for v in cv if is_plp(v["clinical_significance"]) and (v["gold_stars"] or 0) >= min_gold_stars]
    plp_in = [v for v in plp if v["in_gnomad"] and _SAFE_ID.match(v["variant_id"])]
    rec.update(status=AVAILABLE, normalized_gene=gene["symbol"], gene_id=gene["gene_id"], chrom=gene["chrom"],
               clinvar_total=len(cv), clinvar_plp=len(plp), clinvar_plp_in_gnomad=len(plp_in), plp_variants=[])
    for i in range(0, len(plp_in), batch):
        chunk = plp_in[i:i + batch]
        res = client.query(_batch_query([v["variant_id"] for v in chunk]))
        got = res.get("data") or {}
        for j, v in enumerate(chunk):
            f = got.get(f"v{j}")
            if not f:
                continue
            ex, ge = _counts(f.get("exome")), _counts(f.get("genome"))
            if ex is None and ge is None:
                continue
            rec["plp_variants"].append({
                "variant_id": parse_variant_id(v["variant_id"]), "gnomad_id": v["variant_id"],
                "clinical_significance": v["clinical_significance"], "gold_stars": v["gold_stars"],
                "exome": ex, "genome": ge})
    return rec


def cached_fetch(client: GnomadClient, symbol: str, cache_dir: Path, **kw) -> dict:
    path = cache_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', symbol)}.json"
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    rec = fetch_gene(client, symbol, **kw)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def summarize_gene(rec: dict) -> Dict:
    """Gene-level statistic: cumulative allele frequency (CAF) of ClinVar P/LP variants.

    CAF = sum over P/LP variants of AC/AN, with exome and genome counts pooled (AC and AN added) where a
    variant is observed in both callsets. 'sas' uses the gnomAD South-Asian ancestry group (NOT IndiGen,
    NOT specifically Indian). CAF == 0 is a real observation: P/LP variants exist in ClinVar but no carrier
    was observed in the sampled gnomAD genomes/exomes.
    """
    out = {"input_gene": rec["input_gene"], "status": rec["status"], "dataset_version": rec.get("dataset", DATASET)}
    if rec["status"] != AVAILABLE:
        return out
    g_caf = s_caf = 0.0
    n_s = 0
    for v in rec["plp_variants"]:
        parts = [p for p in (v["exome"], v["genome"]) if p]
        ac, an = sum(p["ac"] for p in parts), sum(p["an"] for p in parts)
        if an > 0:
            g_caf += ac / an
        sp = [p for p in parts if p["sas_an"]]
        if sp:
            sac, san = sum(p["sas_ac"] for p in sp), sum(p["sas_an"] for p in sp)
            if san > 0:
                s_caf += sac / san
                n_s += 1
    out.update(normalized_gene=rec["normalized_gene"], clinvar_total=rec["clinvar_total"], clinvar_plp=rec["clinvar_plp"],
               clinvar_plp_in_gnomad=rec["clinvar_plp_in_gnomad"], n_plp_with_counts=len(rec["plp_variants"]),
               caf_global=g_caf, caf_sas=s_caf, n_variants_sas=n_s,
               has_plp=rec["clinvar_plp"] > 0)
    return out
