"""Canonical variant representation: chr:pos:ref:alt on GRCh38 (no 'chr' prefix, upper-case alleles).

Variants are matched on this ID, never on gene symbol alone. rsIDs are not coordinates and are not
converted (that would need dbSNP); they normalise to None.
"""
import re
from typing import List, Optional

_CHROMS = {str(i) for i in range(1, 23)} | {"X", "Y", "M"}
_ALLELE = re.compile(r"^[ACGTN]+$")


def normalize_chromosome(chrom) -> Optional[str]:
    c = str(chrom).strip()
    c = re.sub(r"^chr", "", c, flags=re.IGNORECASE).upper()
    if c == "MT":
        c = "M"
    return c if c in _CHROMS else None


def normalize_variant(chrom, pos, ref, alt) -> Optional[str]:
    """Return canonical ID or None if any component is invalid (never guesses)."""
    c = normalize_chromosome(chrom)
    try:
        p = int(str(pos).strip())
    except (TypeError, ValueError):
        return None
    r, a = str(ref).strip().upper(), str(alt).strip().upper()
    if c is None or p <= 0 or not _ALLELE.match(r) or not _ALLELE.match(a) or r == a:
        return None
    return f"{c}:{p}:{r}:{a}"


def split_multiallelic(chrom, pos, ref, alts: str) -> List[Optional[str]]:
    """'A,G' -> one canonical ID per alternate allele (None for invalid alleles such as '*')."""
    return [normalize_variant(chrom, pos, ref, a) for a in str(alts).split(",")]


def parse_variant_id(text: str) -> Optional[str]:
    """Accepts 'chr1-100-A-T', '1:100:A:T', '1_100_A_T' -> canonical ID."""
    parts = re.split(r"[-:_]", str(text).strip())
    return normalize_variant(*parts) if len(parts) == 4 else None
