import re

class VariantNormalizer:
    def __init__(self):
        pass

    def normalize_variant(self, raw_id, chr_val=None, pos_val=None, ref_val=None, alt_val=None, gene=None, source="unknown"):
        """
        Builds a standardized representation of a genomic variant:
        chrom:pos:ref:alt (e.g. 15:28123456:A:G) or rsID if coordinates are missing.
        """
        raw_str = str(raw_id).strip() if raw_id is not None else ""
        
        norm_chr = str(chr_val).replace("chr", "").strip() if chr_val is not None else ""
        norm_pos = str(pos_val).strip() if pos_val is not None else ""
        norm_ref = str(ref_val).strip().upper() if ref_val is not None else ""
        norm_alt = str(alt_val).strip().upper() if alt_val is not None else ""

        if norm_chr and norm_pos and norm_ref and norm_alt:
            normalized_id = f"{norm_chr}:{norm_pos}:{norm_ref}:{norm_alt}"
        elif raw_str.startswith("rs"):
            normalized_id = raw_str
        elif ":" in raw_str:
            parts = raw_str.replace("chr", "").split(":")
            if len(parts) >= 4:
                normalized_id = f"{parts[0]}:{parts[1]}:{parts[2].upper()}:{parts[3].upper()}"
            else:
                normalized_id = raw_str
        else:
            normalized_id = raw_str if raw_str else "variant_unknown"

        return {
            "original_identifier": raw_str,
            "normalized_identifier": normalized_id,
            "chromosome": norm_chr,
            "position": norm_pos,
            "reference": norm_ref,
            "alternate": norm_alt,
            "gene": gene or "UNKNOWN",
            "source": source
        }
