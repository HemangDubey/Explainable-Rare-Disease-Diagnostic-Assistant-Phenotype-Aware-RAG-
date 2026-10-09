"""Build traceable evidence packets from REAL upstream outputs (Phase 2R retrieval + Phase 3R ranking).

Nothing is computed or invented here that the upstream stages did not produce: scores are copied, never recomputed
except for the score-breakdown reproduction check. Every evidence item has a stable id (C<rank>-E<n>), a plain-text
statement generated deterministically from data, and a source identifier. Missing information is an explicit
`unavailable` item, never a guess. Literature is NOT collected in this phase and no citation is ever generated.
"""
import re
from typing import Any, Dict, List, Optional

from src.reasoning.labels import completeness, overlap_label

_NEG = re.compile(r"\b(no|denies|denied|without|absence of|absent|negative for|not)\b", re.IGNORECASE)
_BREAK = re.compile(r"[.;:\n]|\bbut\b|\bhowever\b|\balthough\b", re.IGNORECASE)


def negated_mentions(clinical_text: str, phenotypes: List[Dict[str, Any]], window: int = 45) -> List[Dict[str, Any]]:
    """Mentions whose preceding clause contains a negation cue (conservative, regex based; NER itself ignores negation)."""
    out = []
    for p in phenotypes or []:
        s = p.get("start")
        if s is None:
            continue
        pre = clinical_text[max(0, s - window):s]
        cut = max((m.end() for m in _BREAK.finditer(pre)), default=0)
        clause = pre[cut:]
        if _NEG.search(clause):
            out.append(p)
    return out


def _fmt(x, nd=4):
    return "unavailable" if x is None else f"{x:.{nd}f}"


class EvidenceBuilder:
    def __init__(self, disease_records: Optional[Dict[str, Dict[str, Any]]] = None, weights: Optional[Dict[str, float]] = None,
                 kb_versions: Optional[Dict[str, str]] = None):
        self.disease_records = disease_records or {}
        self.weights = weights or {}
        self.kb_versions = kb_versions or {}

    # ------------------------------------------------------------------------------------------------
    def score_breakdown(self, cand: Dict[str, Any]) -> Dict[str, Any]:
        w = self.weights
        w_h, w_r, w_p = w.get("w_phenotype"), w.get("w_retrieval"), w.get("w_population")
        ref = w.get("population_reference", 0.5)
        ph, rt = cand.get("phenotype_score"), cand.get("retrieval_score")
        pop = cand.get("population") or {}
        sig = pop.get("signal")
        out = {"phenotype_score": ph, "retrieval_score": rt, "weights": {"w_phenotype": w_h, "w_retrieval": w_r, "w_population": w_p,
               "population_reference": ref}, "base_score": cand.get("base_score"), "population_status": pop.get("status"),
               "population_signal": sig, "population_contribution": cand.get("population_contribution"),
               "final_score": cand.get("final_score"), "rank": cand.get("rank"), "baseline_rank": cand.get("baseline_rank"),
               "rank_change": cand.get("rank_change")}
        if None not in (ph, rt, w_h, w_r) and cand.get("final_score") is not None:
            base = w_h * ph + w_r * rt
            contrib = (w_p * (sig - ref)) if (sig is not None and w_p) else 0.0
            out["recomputed_base_score"] = round(base, 6)
            out["recomputed_final_score"] = round(base + contrib, 6)
            out["matches_backend"] = abs(out["recomputed_final_score"] - cand["final_score"]) < 1e-5
        else:
            out["matches_backend"] = None
        if not w_p:
            out["population_note"] = "w_population = 0: population evidence did not modify the ranking."
        elif sig is None:
            out["population_note"] = "No population signal for this candidate; no population adjustment was applied."
        else:
            out["population_note"] = "Population evidence adjusted the final score by the contribution shown (separate from base score)."
        return out

    # ------------------------------------------------------------------------------------------------
    def build(self, cand: Dict[str, Any], rank: int, hpo_terms: List[Dict[str, Any]], phenotypes: List[Dict[str, Any]],
              clinical_text: str = "", retrieval_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rm = retrieval_metadata or {}
        did = cand.get("disease_id")
        rec = self.disease_records.get(did, {})
        annotated_ids = list(rec.get("hpo_ids") or [])
        annotated_names = list(rec.get("hpo_names") or [])
        name_of = dict(zip(annotated_ids, annotated_names))
        genes = list(cand.get("associated_genes") or rec.get("genes") or [])
        src_db = cand.get("source_db") or rec.get("source_db") or (did.split(":")[0] if did and ":" in did else None)
        prefix = f"C{rank}-E"
        items: List[Dict[str, Any]] = []

        def add(typ, text, source, **data):
            items.append({"id": f"{prefix}{len(items) + 1}", "type": typ, "text": text, "source": source, "data": data})
            return items[-1]["id"]

        neg = negated_mentions(clinical_text, phenotypes)
        neg_ids = {p.get("hpo_id") for p in neg if p.get("hpo_id")}
        patient_terms = [h for h in hpo_terms if h.get("hpo_id")]
        mention_of = {h["hpo_id"]: h.get("mention") for h in patient_terms}
        matched_ids = [h for h in (cand.get("matched_hpo_ids") or []) if h not in neg_ids]
        patient_ids = [h["hpo_id"] for h in patient_terms if h["hpo_id"] not in neg_ids]

        # --- retrieval ---------------------------------------------------------------------------------
        add("retrieval", f"Retrieved by strategy '{rm.get('strategy', 'unknown')}' over {rm.get('model_name', rm.get('model', 'unknown model'))}; "
            f"retrieval score {_fmt(cand.get('retrieval_score'))}. This is a rank-based similarity score, not a probability.",
            f"retrieval:{rm.get('model', 'unknown')}", retrieval_score=cand.get("retrieval_score"), strategy=rm.get("strategy"))

        # --- phenotype matches / unverified -------------------------------------------------------------
        supporting_ids = []
        for hid in matched_ids:
            term = next((h for h in patient_terms if h["hpo_id"] == hid), {})
            supporting_ids.append(add(
                "phenotype_match",
                f"Patient mention '{mention_of.get(hid)}' maps to {hid} ({term.get('name')}; {term.get('matching_method')}), "
                f"which is annotated to {cand.get('disease_name')} ({did}).",
                f"HPO annotation {did} -> {hid}", hpo_id=hid, term=term.get("name"), mention=mention_of.get(hid),
                mapping_method=term.get("matching_method"), mapping_score=term.get("score")))
        unmatched_patient = [h for h in patient_terms if h["hpo_id"] not in set(matched_ids) and h["hpo_id"] not in neg_ids]
        unverified_ids = []
        for h in unmatched_patient:
            unverified_ids.append(add("patient_phenotype_not_annotated",
                                      f"Patient phenotype {h['hpo_id']} ({h.get('name')}) is not annotated to {cand.get('disease_name')} in the knowledge base "
                                      f"(this does not mean the disease cannot cause it).", f"HPO annotation {did}", hpo_id=h["hpo_id"]))
        not_stated = [(i, name_of.get(i, i)) for i in annotated_ids if i not in set(patient_ids) and i not in neg_ids]
        if annotated_ids:
            shown = not_stated[:8]
            if shown:
                unverified_ids.append(add(
                    "disease_phenotype_unverified",
                    f"{len(not_stated)} phenotype(s) annotated to {cand.get('disease_name')} are not stated in the patient record "
                    f"(e.g. {', '.join(n for _, n in shown)}); their absence is not established.",
                    f"HPO annotation {did}", hpo_ids=[i for i, _ in shown], names=[n for _, n in shown], total=len(not_stated)))
        else:
            unverified_ids.append(add("disease_phenotypes_unavailable", f"No HPO phenotype annotations are available for {did} in the knowledge base record.",
                                      f"knowledge base record {did}"))

        # --- contradictory evidence (only explicit patient negations) ------------------------------------
        contra_ids = []
        for p in neg:
            hid = p.get("hpo_id")
            if hid and hid in annotated_ids:
                contra_ids.append(add(
                    "contradiction",
                    f"The patient record appears to negate '{p.get('mention')}' ({hid}), which is annotated to {cand.get('disease_name')}. "
                    f"Annotation frequency is not considered; a single absent finding does not exclude the disease.",
                    f"patient text (negation cue before span {p.get('start')}-{p.get('end')}) vs HPO annotation {did} -> {hid}", hpo_id=hid))

        # --- genetic -------------------------------------------------------------------------------------
        gene_ids = []
        if genes:
            gene_ids.append(add("gene_association", f"The knowledge base associates {', '.join(genes)} with {cand.get('disease_name')} ({did}).",
                                f"HPO phenotype_to_genes ({src_db} record {did})", genes=genes))
        else:
            gene_ids.append(add("gene_association_unavailable", f"No gene association is recorded for {did} in the knowledge base.", f"knowledge base record {did}"))
        add("variant_evidence_unavailable", "No patient variant data was provided; no variant-level genetic evidence is available.", "patient input")

        # --- population ----------------------------------------------------------------------------------
        pop = cand.get("population") or {}
        pop_ids = []
        for key, label in (("gnomad_south_asian", "gnomAD South Asian"), ("gnomad_global", "gnomAD global"), ("indigen", "IndiGen")):
            ev = pop.get(key) or {}
            st = ev.get("status", "unavailable")
            if st == "available" and ev.get("caf") is not None:
                pop_ids.append(add("population_evidence",
                                   f"{label}: cumulative allele frequency of ClinVar pathogenic/likely-pathogenic variants in the associated gene(s) = {ev['caf']:.3e} "
                                   f"(gene-level; population frequency is not a disease probability).",
                                   f"{label} ({'gnomAD v4.1 exomes + ClinVar' if 'gnomAD' in label else 'IndiGen'})", caf=ev["caf"], population=label))
            else:
                reason = {"unavailable": "unavailable", "not_found": "no usable record", "not_applicable": "not applicable (no associated gene)"}.get(st, st)
                pop_ids.append(add("population_unavailable", f"{label} population evidence: {reason}."
                                   + (" Access to the IndiGen dataset is required." if key == "indigen" and st == "unavailable" else ""),
                                   f"{label}", status=st))

        sb = self.score_breakdown({**cand, "rank": rank})
        add("score_breakdown", f"Base score {_fmt(sb['base_score'])} = {sb['weights']['w_phenotype']} x phenotype {_fmt(sb['phenotype_score'])} + "
            f"{sb['weights']['w_retrieval']} x retrieval {_fmt(sb['retrieval_score'])}; population contribution {_fmt(sb['population_contribution'])}; "
            f"final {_fmt(sb['final_score'])}; rank {rank}. {sb['population_note']}", "ranking pipeline (Phase 3R)", **{k: v for k, v in sb.items() if k != "population_note"})

        lbl = overlap_label(len(matched_ids), len(patient_ids), has_conflict=bool(contra_ids))
        pop_avail = any((pop.get(k) or {}).get("status") == "available" for k in ("gnomad_south_asian", "gnomad_global", "indigen"))
        comp = completeness({"phenotype overlap": bool(matched_ids), "gene association": bool(genes), "population evidence": pop_avail})
        return {
            "candidate_id": did, "disease_name": cand.get("disease_name"), "rank": rank, "baseline_rank": cand.get("baseline_rank"),
            "source_db": src_db, "evidence": items, "evidence_ids": [i["id"] for i in items],
            "groups": {"supporting": supporting_ids, "unverified": unverified_ids, "contradictory": contra_ids, "genetic": gene_ids, "population": pop_ids},
            "labels": lbl, "completeness": comp, "score_breakdown": sb, "genes": genes,
            "matched_phenotypes": [{"hpo_id": h, "name": next((t.get("name") for t in patient_terms if t["hpo_id"] == h), h)} for h in matched_ids],
            "negated_mentions": [{"mention": p.get("mention"), "hpo_id": p.get("hpo_id")} for p in neg],
        }
