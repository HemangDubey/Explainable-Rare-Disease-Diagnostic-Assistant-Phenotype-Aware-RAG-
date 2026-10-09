"""Builds the Digital Twin payload from a STORED, owner-scoped case. Nothing is invented: every finding, candidate, gene value and graph
edge is read from the case produced by the existing pipeline (NER -> HPO -> retrieval -> Phase 3R ranking -> Phase 4R fusion) or from the
existing ClinVar/gnomAD gene cache. Missing data is returned as an explicit status, never filled in.
"""
import math
from typing import Any, Callable, Dict, List, Optional

from src.scribe.note_structurer import _subject, mention_flags, split_statements
from src.twin.anatomy import REGIONS, AnatomyMapper

MAPPED = ("exact", "synonym", "lexical", "semantic", "exact_after_modifier_strip", "synonym_after_modifier_strip")
REVIEW_STATUSES = ("present", "negated", "uncertain", "pending")


def finding_id(i: int, p: Dict[str, Any]) -> str:
    s, e = p.get("start"), p.get("end")
    return f"F{i}" + (f"_{s}_{e}" if isinstance(s, int) and isinstance(e, int) else "")


def assess_assertion(text: str, start: Optional[int], end: Optional[int]) -> Dict[str, Any]:
    """Rule-based assertion (the scribe's negation/uncertainty/relationship rules), applied within the sentence holding the mention."""
    if not text or not isinstance(start, int) or not isinstance(end, int):
        return {"status": "pending", "subject": "patient", "method": "not_assessed (no text offsets stored for this finding)"}
    for st in split_statements(text):
        if st["start"] <= start and end <= st["end"] + 1:
            fl = mention_flags(st["text"], start - st["start"], min(end, st["end"]) - st["start"])
            subj = _subject(st["text"])
            status = "negated" if fl["negated"] else ("uncertain" if fl["uncertain"] else ("pending" if fl["pending"] else "present"))
            return {"status": status, "subject": subj["subject"], "relationship": subj["relationship"],
                    "method": "rule-based (negation/uncertainty/relationship cues in the same sentence); unverified"}
    return {"status": "pending", "subject": "patient", "method": "mention outside sentence spans"}


def display_state(mapped: bool, subject: str, status: str, verified: bool) -> str:
    if not mapped:
        return "unmapped"
    if subject == "relative":
        return "relative_finding"
    if status == "negated":
        return "negated"
    if status == "uncertain":
        return "uncertain"
    if status == "pending":
        return "pending"
    return "confirmed" if verified else "unverified"


def build_findings(case: Dict[str, Any], mapper: AnatomyMapper) -> List[Dict[str, Any]]:
    text = case.get("clinical_text", "") or ""
    review = case.get("phenotype_review", {}) or {}
    out = []
    for i, p in enumerate(case.get("extracted_phenotypes", []) or []):
        fid = finding_id(i, p)
        hid = p.get("hpo_id")
        mapped = bool(hid) and p.get("mapping_status", "exact") in MAPPED
        a = assess_assertion(text, p.get("start"), p.get("end"))
        r = review.get(fid, {})
        status = r.get("status") if r.get("status") in REVIEW_STATUSES else a["status"]
        verified = bool(r.get("verified"))
        regions = mapper.regions_for(hid) if mapped else []
        out.append({
            "finding_id": fid, "text_span": p.get("mention") or p.get("phenotype"), "start": p.get("start"), "end": p.get("end"),
            "hpo_id": hid if mapped else None, "hpo_label": (p.get("hpo_term") or p.get("phenotype")) if mapped else None,
            "normalization": {"status": p.get("mapping_status", "unknown"), "method": p.get("matching_method"), "score": p.get("mapping_score")},
            "ner_confidence": p.get("confidence"),
            "assertion": a, "status": status, "status_source": "clinician" if r.get("status") in REVIEW_STATUSES else "rule-based",
            "verified": verified, "reviewed_at": r.get("reviewed_at"),
            "display_state": display_state(mapped, a.get("subject", "patient"), status, verified),
            "regions": regions, "unassigned": mapped and not regions,
            "provenance": {"source": "clinical text of this case", "ner": "BiomedBERT phenotype NER", "normalizer": "HPO normaliser (Phase 2R)"},
        })
    return out


def _candidate(c: Dict[str, Any]) -> Dict[str, Any]:
    pe = c.get("phenotype_evidence") or {}
    pk = c.get("packet") or {}
    return {
        "disease_id": c.get("disease_id"), "disease_name": c.get("disease_name"), "rank": c.get("rank"),
        "final_score": c.get("final_score"), "phenotype_score": c.get("phenotype_score"), "retrieval_score": c.get("retrieval_score"),
        "population_contribution": c.get("population_contribution"), "label": (c.get("labels") or {}).get("label") or pe.get("label"),
        "matched_hpo": [{"hpo_id": m.get("hpo_id"), "name": m.get("name")} for m in pe.get("matched_phenotypes", []) if isinstance(m, dict)],
        "disease_annotations_not_in_record": pe.get("missing_phenotypes", []),
        "genes": c.get("genes", []), "score_breakdown": c.get("score_breakdown"),
        "evidence": [{"id": e.get("id"), "type": e.get("type"), "text": e.get("text"), "source": e.get("source"),
                      "hpo_id": (e.get("data") or {}).get("hpo_id")} for e in pk.get("evidence", [])],
        "score_note": "Rank-based prioritisation score, not a probability.",
    }


def _gene_evidence(symbol: str, gene_record: Optional[Callable], gene_lookup: Optional[Callable], max_variants: int = 25,
                   clinvar_records: Optional[List[Dict[str, Any]]] = None, clinvar_meta: Optional[Dict[str, Any]] = None,
                   gnomad_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gene-level REFERENCE evidence (never the patient's genotype). With `clinvar_records` (from GeneEvidenceService) ClinVar is built
    from every ClinVar P/LP record of the gene and gnomAD counts are merged per variant; without them the older cache-only path is used."""
    out = {"gene": symbol, "patient_variant": {"status": "not_provided",
                                               "note": "No patient genotype or variant data exists in this case (the case workflow has no variant input)."}}
    info = gene_lookup(symbol) if gene_lookup else None
    rec = gene_record(symbol) if gene_record else None
    g = (info or {}).get("gnomad") or {}
    if g.get("status") == "available":
        meta = {"dataset": g.get("dataset_version"), "release": "gnomAD v4.1", "callset": "exomes (FILTER=PASS)",
                "reference_genome": (rec or {}).get("reference_genome", "GRCh38"), "retrieved_at": (rec or {}).get("fetched_at"),
                "clinvar_plp_variants": (rec or {}).get("clinvar_plp"), "observed_in_gnomad": (rec or {}).get("clinvar_plp_in_gnomad"),
                "non_pass_excluded": (rec or {}).get("non_pass_variants"),
                "transcript": "not applicable (variant-level counts joined by GRCh38 position/allele; no transcript annotation)",
                "statistic": "cumulative allele frequency of ClinVar P/LP variants (gene level)"}
        out["gnomad_global"] = {"status": "available", "cumulative_af": g.get("caf_global"), **meta}
        out["gnomad_south_asian"] = {"status": "available", "cumulative_af": g.get("caf_sas"), **meta,
                                     "note": "gnomAD South Asian ancestry group; not an India-specific dataset"}
    else:
        st = (gnomad_state or {}).get("status")
        if st in ("not_ingested", "error", "not_found"):
            blk = {"status": st, "reason": gnomad_state.get("reason")}
            if gnomad_state.get("at"):
                blk["at"] = gnomad_state["at"]
        elif rec is not None and rec.get("status") == "not_found":
            blk = {"status": "not_found", "reason": rec.get("reason")}
        else:
            blk = {"status": g.get("status", "unavailable"), "reason": g.get("reason")}
        out["gnomad_global"], out["gnomad_south_asian"] = dict(blk), dict(blk)
    ind = (info or {}).get("indigen") or {"status": "unavailable"}
    if ind.get("status") == "available":          # only when an authorised IndiGen export has been ingested (src/population/indigen_adapter.py)
        out["indigen"] = {"status": "available", "cumulative_af": ind.get("caf"), "n_variants_found": ind.get("n_variants_found"),
                          "dataset": ind.get("dataset_version"), "source": "IndiGen (CSIR-IGIB), user-supplied authorised export"}
    else:
        missing_dataset = ind.get("status") in (None, "unavailable")
        out["indigen"] = {"status": "unavailable" if missing_dataset else ind.get("status"),
                          "reason": "IndiGen dataset not available (access required)" if missing_dataset
                          else (ind.get("reason") or "gene not found in the IndiGen export"),
                          "substitution": "none — gnomAD South Asian is a different dataset and is never shown as IndiGen"}

    def counts(v):
        ex = (v or {}).get("exome") or {}
        an, san = ex.get("an") or 0, ex.get("sas_an") or 0
        return {"af_global": (ex.get("ac", 0) / an) if an else None, "af_south_asian": (ex.get("sas_ac", 0) / san) if san else None,
                "ac_global": ex.get("ac"), "an_global": ex.get("an"), "ac_south_asian": ex.get("sas_ac"), "an_south_asian": ex.get("sas_an")}

    cached = rec is not None and rec.get("status") == "available"
    if clinvar_records is not None:
        by_id = {v["variant_id"]: v for v in (rec or {}).get("plp_variants", [])} if cached else {}
        vs = []
        for c in clinvar_records:
            hit = by_id.get(c["variant_id"])
            row = {**c, "in_gnomad": (hit is not None) if cached else None}
            row.update(counts(hit) if hit else {"af_global": None, "af_south_asian": None})
            vs.append(row)
        if vs:
            vs.sort(key=lambda x: (-(x["gold_stars"] or 0), x["af_global"] is None, -(x["af_global"] or 0), x["variant_id"]))
            m = clinvar_meta or {}
            out["clinvar"] = {"status": "available", "source": m.get("source"), "reference_genome": "GRCh38", "release": m.get("file_last_modified"),
                              "processed_at": m.get("processed_at"), "filters": m.get("filters"),
                              "clinvar_total_variants": m.get("clinvar_total_variants"), "clinvar_plp_variants": len(vs),
                              "variants": vs[:max_variants], "variants_shown": min(len(vs), max_variants),
                              "gnomad_join": "observed / not observed in gnomAD v4.1 exomes" if cached else "gnomAD counts not fetched yet",
                              "note": "Reference ClinVar variants known for this gene. None of them was detected in this patient."}
        else:
            out["clinvar"] = {"status": "not_found", "reason": "ClinVar has no germline P/LP GRCh38 record with >=1 review star for this gene"}
    elif cached:
        vs = []
        for v in rec.get("plp_variants", []) or []:
            row = {"variant_id": v.get("variant_id"), "clinvar_variation_id": v.get("clinvar_variation_id"),
                   "clinical_significance": v.get("clinical_significance"), "review_status": v.get("review_status"),
                   "gold_stars": v.get("gold_stars"), "in_gnomad": True}
            row.update(counts(v))
            vs.append(row)
        vs.sort(key=lambda x: (-(x["gold_stars"] or 0), -(x["af_global"] or 0)))
        out["clinvar"] = {"status": "available", "source": rec.get("source"), "reference_genome": rec.get("reference_genome"),
                          "clinvar_total_variants": rec.get("clinvar_total"), "clinvar_plp_variants": rec.get("clinvar_plp"),
                          "variants": vs[:max_variants], "variants_shown": min(len(vs), max_variants),
                          "note": "Reference ClinVar variants known for this gene. None of them was detected in this patient."}
    else:
        out["clinvar"] = {"status": "unavailable", "reason": "gene not in the ClinVar/gnomAD gene cache"}
    out["population_comparison"] = population_comparison(out)
    return out


def _log2_ratio(a, b):
    return math.log2(a / b) if a and b and a > 0 and b > 0 else None


def population_comparison(gene_ev: Dict[str, Any]) -> Dict[str, Any]:
    """Side-by-side population evidence for one gene, built only from values already in `gene_ev`. Each column keeps its own source
    and status; a missing column stays missing (it is never filled from another population)."""
    g, s, ind = gene_ev["gnomad_global"], gene_ev["gnomad_south_asian"], gene_ev["indigen"]
    col = lambda e, label, src: {"label": label, "source": src, "status": e.get("status"),  # noqa: E731
                                 "cumulative_af": e.get("cumulative_af") if e.get("status") == "available" else None}
    cols = [col(g, "gnomAD Global", "gnomAD v4.1 exomes"), col(s, "gnomAD South Asian", "gnomAD v4.1 exomes, South Asian ancestry group"),
            col(ind, "IndiGen", "IndiGen (CSIR-IGIB)")]
    variants = []
    cv = gene_ev.get("clinvar") or {}
    for v in cv.get("variants", []) if cv.get("status") == "available" else []:
        if v.get("in_gnomad") is False or (v.get("af_global") is None and v.get("af_south_asian") is None):
            continue                                  # not observed / not fetched: nothing comparable to show for this variant
        variants.append({"variant_id": v["variant_id"], "clinical_significance": v["clinical_significance"],
                         "af_global": v["af_global"], "af_south_asian": v["af_south_asian"],
                         "log2_sas_vs_global": _log2_ratio(v["af_south_asian"], v["af_global"])})
    available = [c["label"] for c in cols if c["status"] == "available"]
    return {
        "columns": cols, "variants": variants,
        "log2_sas_vs_global": _log2_ratio(cols[1]["cumulative_af"], cols[0]["cumulative_af"]),
        "status": "available" if len(available) >= 2 else ("partial" if available else "unavailable"),
        "note": "Reference allele frequencies of ClinVar P/LP variants in each population; not this patient's genotype. "
                "gnomAD South Asian is not India-specific and is not a substitute for IndiGen.",
    }


def population_sources(gene_lookup_available: bool, indigen_available: bool = False) -> List[Dict[str, Any]]:
    """Provenance of every population source the twin can show, with its current status."""
    return [
        {"source": "ClinVar", "role": "pathogenic / likely-pathogenic reference variants per gene", "status": "available" if gene_lookup_available else "unavailable",
         "provenance": "ClinVar variant_summary (GRCh38, germline, >=1 review star); data/processed/population/clinvar_provenance.json"},
        {"source": "gnomAD Global", "role": "allele counts of those variants, all ancestries", "status": "available" if gene_lookup_available else "unavailable",
         "provenance": "gnomAD v4.1 exomes per-gene cache (data/raw/gnomad/gene_cache)"},
        {"source": "gnomAD South Asian", "role": "allele counts in the gnomAD South Asian ancestry group (not India-specific)",
         "status": "available" if gene_lookup_available else "unavailable", "provenance": "same gnomAD v4.1 exomes cache, sas_ac / sas_an"},
        {"source": "IndiGen", "role": "Indian population allele frequencies", "status": "available" if indigen_available else "unavailable",
         "provenance": ("authorised export ingested by src/population/indigen_adapter.py" if indigen_available else
                        "not present. Access is granted by CSIR-IGIB (https://clingen.igib.res.in/indigen); place an authorised VCF/TSV export in "
                        "data/raw/indigen/ and run the ingest. Nothing is substituted while it is missing.")},
    ]


def build_graph(findings, candidates) -> Dict[str, Any]:
    nodes, edges, seen = [], [], set()

    def add(n):
        if n["id"] not in seen:
            seen.add(n["id"])
            nodes.append(n)
    for f in findings:
        add({"id": "f:" + f["finding_id"], "type": "finding", "label": f["text_span"], "state": f["display_state"],
             "detail": {"kind": "patient observation", "hpo_id": f["hpo_id"], "status": f["status"], "verified": f["verified"]}})
        if f["hpo_id"]:
            add({"id": "h:" + f["hpo_id"], "type": "hpo", "label": f["hpo_label"], "detail": {"kind": "HPO concept", "hpo_id": f["hpo_id"]}})
            edges.append({"source": "f:" + f["finding_id"], "target": "h:" + f["hpo_id"], "type": "normalized_to",
                          "detail": f["normalization"]})
    hpo_in_case = {f["hpo_id"] for f in findings if f["hpo_id"]}
    for c in candidates:
        did = "d:" + str(c["disease_id"])
        add({"id": did, "type": "disease", "label": c["disease_name"], "rank": c["rank"],
             "detail": {"kind": "retrieved disease candidate (not a diagnosis)", "final_score": c["final_score"], "label": c["label"]}})
        for ev in c["evidence"]:
            if ev["type"] == "phenotype_match":
                hid = ev.get("hpo_id")
                if hid and hid in hpo_in_case:        # only HPO concepts that are actually in this patient's record
                    edges.append({"source": "h:" + hid, "target": did, "type": "annotated_to", "evidence_id": ev["id"],
                                  "detail": {"text": ev["text"], "source": ev["source"]}})
            if ev["type"] == "gene_association":
                for g in c["genes"]:
                    if g in (ev["text"] or ""):
                        add({"id": "g:" + g, "type": "gene", "label": g, "detail": {"kind": "gene associated with the disease (knowledge base)"}})
                        edges.append({"source": did, "target": "g:" + g, "type": "gene_association", "evidence_id": ev["id"],
                                      "detail": {"text": ev["text"], "source": ev["source"]}})
    return {"nodes": nodes, "edges": edges,
            "literature": {"status": "not_retrieved", "note": "No literature has been retrieved for this case; no publication nodes are shown."}}


def build_twin(case_id: str, case: Dict[str, Any], mapper: AnatomyMapper, gene_record=None, gene_lookup=None, scenarios=None,
               top_k: int = 5, indigen_available: bool = False, gene_evidence=None) -> Dict[str, Any]:
    findings = build_findings(case, mapper)
    cands = [_candidate(c) for c in (case.get("fused_candidates") or [])[:top_k]]
    genes = []
    for c in cands:
        for g in c["genes"]:
            if g not in genes:
                genes.append(g)
    regions: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        for r in f["regions"]:
            e = regions.setdefault(r["region"], {"region": r["region"], **{k: v for k, v in REGIONS[r["region"]].items()}, "findings": []})
            e["findings"].append({"finding_id": f["finding_id"], "display_state": f["display_state"]})
    counts: Dict[str, int] = {}
    for f in findings:
        counts[f["display_state"]] = counts.get(f["display_state"], 0) + 1
    return {
        "case": {"case_id": case_id, "clinical_text": case.get("clinical_text", ""), "origin": case.get("origin", "diagnosis"),
                 "has_ranking": bool(cands), "state_counts": counts},
        "findings": findings, "regions": list(regions.values()),
        "unassigned_findings": [f["finding_id"] for f in findings if f["unassigned"]],
        "candidates": cands,
        "genomic": {"genes": [gene_evidence(g) if gene_evidence else _gene_evidence(g, gene_record, gene_lookup) for g in genes[:12]],
                    "sources": population_sources(gene_lookup is not None, indigen_available),
                    "note": "Gene-level reference evidence for the candidates' associated genes. No patient variant is known."},
        "graph": build_graph(findings, cands),
        "scenarios": scenarios or [],
        "mapping": {"rule": "HPO is_a ancestor -> organ-system table (src/twin/anatomy.py); most specific entry kept; otherwise unassigned",
                    "region_catalogue": REGIONS},
        "disclaimer": "Research prototype. Candidates are computational prioritisations, not diagnoses. Only clinician-verified present findings "
                      "are shown as confirmed. Disease annotations are not patient findings.",
    }
