"""Real gnomAD v4.1 EXOME allele counts for ClinVar P/LP variants, read from the official public VCFs.

Source: https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/exomes/gnomad.exomes.v4.1.sites.<chr>.vcf.bgz
(public bucket, no login). Only the compressed blocks covering each gene's P/LP variants are read (HTTP range
requests through the tabix index); no whole-file download. Counts used: AC, AN (global) and AC_sas, AN_sas
(gnomAD South Asian genetic-ancestry group). Only FILTER=PASS records are counted. Genome-callset counts are NOT
included (documented limitation: variants seen only in the genome callset are not counted).
Per-gene records keep the earlier JSON layout so the lookup/scoring code is unchanged.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.population.population_schema import AVAILABLE, NOT_FOUND
from src.population.remote_tabix import RemoteTabix

BASE = "https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/exomes/gnomad.exomes.v4.1.sites.{chrom}.vcf.bgz"
DATASET = "gnomad_v4.1_exomes"
_KEYS = re.compile(r"(?:^|;)(AC|AN|AC_sas|AN_sas)=([^;]*)")
_readers, _lock = {}, threading.Lock()


def reader(chrom: str) -> RemoteTabix:
    with _lock:
        if chrom not in _readers:
            _readers[chrom] = RemoteTabix(BASE.format(chrom=chrom))
        return _readers[chrom]


def parse_lines(lines):
    """-> {(pos, ref, alt): {ac, an, sas_ac, sas_an, filter}}; multi-allelic sites are split per ALT allele."""
    out = {}
    for ln in lines:
        f = ln.split("\t", 8)
        info = dict(_KEYS.findall(f[7]))
        for i, alt in enumerate(f[4].split(",")):
            def pick(k):
                v = info.get(k)
                if v is None:
                    return None
                parts = v.split(",")
                return int(parts[i] if len(parts) > 1 else parts[0])
            out[(int(f[1]), f[3], alt)] = {
                "ac": pick("AC"), "an": int(info["AN"]) if "AN" in info else None,
                "sas_ac": pick("AC_sas"), "sas_an": int(info["AN_sas"]) if "AN_sas" in info else None,
                "filter": f[6]}
    return out


CLUSTER_GAP = 20000


def gene_regions(df_gene: pd.DataFrame, gap=CLUSTER_GAP):
    """Per chromosome: list of (min,max) position clusters of the gene's P/LP variants (gap-separated)."""
    by_chrom = {}
    for vid in df_gene["variant_id"].unique():
        c, p, _, _ = vid.split(":")
        by_chrom.setdefault(c, []).append(int(p))
    out = {}
    for c, ps in by_chrom.items():
        ps = sorted(set(ps)); regs = []; lo = hi = ps[0]
        for p in ps[1:]:
            if p - hi > gap:
                regs.append((lo, hi)); lo = hi = p
            else:
                hi = p
        regs.append((lo, hi)); out[c] = regs
    return out


def estimate_bytes(plp: pd.DataFrame, genes) -> dict:
    """Upper bound of compressed bytes to read, computed from the tabix indexes only (no data is read)."""
    total, per = 0, {}
    by_gene = {g: d for g, d in plp.groupby("gene")}
    for g in genes:
        sub = by_gene.get(g)
        if sub is None:
            continue
        b = 0
        for c, regs in gene_regions(sub).items():
            if c in ("M", "Y"):
                continue
            for lo, hi in regs:
                b += reader(f"chr{c}").estimate_bytes(f"chr{c}", lo - 1, hi)
        per[g] = b
        total += b
    return {"total_bytes_upper_bound": total, "genes": len(per), "per_gene": per}


def fetch_gene(gene: str, plp_gene: pd.DataFrame, clinvar_total: int, symbol_seen: bool) -> dict:
    rec = {"input_gene": gene, "dataset": DATASET, "reference_genome": "GRCh38", "source": "ClinVar + gnomAD v4.1 exome VCF",
           "fetched_at": datetime.now(timezone.utc).isoformat()}
    if not symbol_seen:
        rec.update(status=NOT_FOUND, reason="gene symbol not present in ClinVar GRCh38 records", plp_variants=[])
        return rec
    rec.update(status=AVAILABLE, normalized_gene=gene, clinvar_total=clinvar_total,
               clinvar_plp=int(plp_gene["variant_id"].nunique()), plp_variants=[], non_pass_variants=0)
    found = {}
    if len(plp_gene):
        for c, regs in gene_regions(plp_gene).items():
            if c in ("M", "Y"):
                continue
            chrom = f"chr{c}"
            for lo, hi in regs:
                try:
                    parsed = parse_lines(reader(chrom).fetch_lines_seek(chrom, lo, hi))
                except Exception as e:  # noqa: BLE001 - recorded so the gene is retried, not silently empty
                    rec.update(status="error", reason=f"{type(e).__name__}: {e}")
                    return rec
                found.update({(c,) + k: v for k, v in parsed.items()})
    for _, r in plp_gene.drop_duplicates("variant_id").iterrows():
        c, p, ref, alt = r["variant_id"].split(":")
        v = found.get((c, int(p), ref, alt))
        if v is None:
            continue
        if v["filter"] != "PASS":
            rec["non_pass_variants"] += 1
            continue
        rec["plp_variants"].append({
            "variant_id": r["variant_id"], "clinical_significance": r["clinical_significance"],
            "review_status": r["review_status"], "gold_stars": int(r["gold_stars"]),
            "clinvar_variation_id": r["variation_id"],
            "exome": {"ac": v["ac"], "an": v["an"], "sas_ac": v["sas_ac"], "sas_an": v["sas_an"]}, "genome": None})
    rec["clinvar_plp_in_gnomad"] = len(rec["plp_variants"])
    return rec


def run(genes, plp_path, totals_path, cache_dir, workers=6, log=print):
    plp = pd.read_parquet(plp_path)
    totals = json.load(open(totals_path))
    by_gene = {g: d for g, d in plp.groupby("gene")}
    cache_dir.mkdir(parents=True, exist_ok=True)
    todo = [g for g in genes if not (cache_dir / f"{g}.json").exists()]
    log(f"{len(genes)} genes, {len(genes) - len(todo)} cached, {len(todo)} to fetch")
    t0, done = time.time(), 0

    def work(g):
        return g, fetch_gene(g, by_gene.get(g, plp.iloc[0:0]), totals.get(g, 0), g in totals)

    with ThreadPoolExecutor(workers) as ex:
        for fu in as_completed([ex.submit(work, g) for g in todo]):
            g, rec = fu.result()
            if rec["status"] != "error":
                (cache_dir / f"{g}.json").write_text(json.dumps(rec), encoding="utf-8")
            done += 1
            if done % 25 == 0 or rec["status"] == "error":
                mb = sum(r.bytes_read for r in _readers.values()) / 1e6
                log(f"[{done}/{len(todo)}] {g}: {rec['status']} in_gnomad={rec.get('clinvar_plp_in_gnomad')} | {mb:.0f} MB read, {time.time() - t0:.0f}s")
    return {"genes_done": done, "bytes_read": sum(r.bytes_read for r in _readers.values())}
