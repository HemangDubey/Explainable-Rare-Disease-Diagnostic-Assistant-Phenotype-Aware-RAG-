"""IndiGen (CSIR-IGIB IndiGenomes) adapter.

IndiGen data is NOT bundled and is never generated. Access is via https://clingen.igib.res.in/indigen
(registration / authors' permission; research use only). If the user obtains a variant-frequency export
(VCF with AC/AN/AF INFO fields, or a TSV with chrom/pos/ref/alt/AC/AN[/AF]) and places it in
data/raw/indigen/, `ingest()` converts it to data/processed/population/indigen_variants.parquet with
provenance. Until then every lookup reports status "unavailable".
"""
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import yaml

from src.population.population_schema import AVAILABLE, NOT_FOUND, UNAVAILABLE
from src.population.variant_normalizer import normalize_variant, split_multiallelic

SOURCE = "IndiGen"


def _parse_info(info: str) -> Dict[str, str]:
    return dict(kv.split("=", 1) for kv in info.split(";") if "=" in kv)


def parse_vcf(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 8:
                continue
            info = _parse_info(c[7])
            ids = split_multiallelic(c[0], c[1], c[3], c[4])
            for i, vid in enumerate(ids):
                if vid is None:
                    continue
                def pick(key):
                    v = info.get(key)
                    return v.split(",")[i] if v is not None and "," in v else v
                ac, an, af = pick("AC"), pick("AN"), pick("AF")
                if ac is None and af is None:
                    continue
                an_i = int(an) if an not in (None, ".") else None
                ac_i = int(ac) if ac not in (None, ".") else None
                af_f = float(af) if af not in (None, ".") else (ac_i / an_i if ac_i is not None and an_i else None)
                yield {"variant_id": vid, "allele_count": ac_i, "allele_number": an_i, "allele_frequency": af_f}


def parse_tsv(path: Path):
    df = pd.read_csv(path, sep="\t", dtype=str)
    cols = {c.lower(): c for c in df.columns}
    need = [cols.get(k) for k in ("chrom", "pos", "ref", "alt")]
    if None in need:
        raise ValueError("TSV needs chrom/pos/ref/alt columns")
    for _, r in df.iterrows():
        vid = normalize_variant(r[need[0]], r[need[1]], r[need[2]], r[need[3]])
        if vid is None:
            continue
        ac = int(r[cols["ac"]]) if "ac" in cols and pd.notna(r[cols["ac"]]) else None
        an = int(r[cols["an"]]) if "an" in cols and pd.notna(r[cols["an"]]) else None
        af = float(r[cols["af"]]) if "af" in cols and pd.notna(r[cols["af"]]) else (ac / an if ac is not None and an else None)
        yield {"variant_id": vid, "allele_count": ac, "allele_number": an, "allele_frequency": af}


def ingest(config_path="configs/config.yaml") -> dict:
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))["population"]
    raw_dir = Path(cfg["indigen_raw_dir"])
    files = [p for p in raw_dir.glob("*") if p.suffix in (".vcf", ".gz", ".tsv", ".txt")] if raw_dir.exists() else []
    if not files:
        return {"source": SOURCE, "status": UNAVAILABLE,
                "reason": f"No IndiGen export found in {raw_dir}. Access must be obtained from CSIR-IGIB; no data is generated."}
    src = files[0]
    rows = list(parse_vcf(src) if src.suffix in (".vcf", ".gz") else parse_tsv(src))
    df = pd.DataFrame(rows).drop_duplicates("variant_id")
    out = Path(cfg["indigen_processed_file"]); out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    prov = {"source": SOURCE, "status": AVAILABLE, "file": src.name, "records": len(df),
            "processed_at": datetime.now(timezone.utc).isoformat(), "processing_script": "src/population/indigen_adapter.py",
            "fields": [c for c in df.columns]}
    (out.parent / "indigen_provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return prov


class IndiGenStore:
    """Variant-level IndiGen lookup. status: available / not_found / unavailable (dataset missing)."""

    def __init__(self, config_path="configs/config.yaml"):
        cfg = yaml.safe_load(open(config_path, encoding="utf-8"))["population"]
        path = Path(cfg["indigen_processed_file"])
        self.df: Optional[Dict[str, dict]] = None
        self.version = None
        if path.exists():
            df = pd.read_parquet(path)
            self.df = {r["variant_id"]: r for r in df.to_dict("records")}
            prov = path.parent / "indigen_provenance.json"
            self.version = json.load(open(prov))["file"] if prov.exists() else path.name

    @property
    def available(self) -> bool:
        return self.df is not None

    def lookup_variant(self, variant_id: str) -> dict:
        if not self.available:
            return {"source": SOURCE, "status": UNAVAILABLE}
        r = self.df.get(variant_id)
        if r is None:
            return {"source": SOURCE, "status": NOT_FOUND, "variant_id": variant_id}
        return {"source": SOURCE, "status": AVAILABLE, "variant_id": variant_id, "dataset_version": self.version,
                "allele_frequency": r.get("allele_frequency"), "allele_count": r.get("allele_count"),
                "allele_number": r.get("allele_number")}
