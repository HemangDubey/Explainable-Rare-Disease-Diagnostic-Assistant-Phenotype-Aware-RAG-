"""Explainable Doctor Copilot: questions answered ONLY from the case's evidence packets.

Guarantees: numbered evidence, schema + grounding validation, per-candidate citations (a point about candidate X may cite only X's
own evidence ids), bounded retries, an explicit provider status with a safe failure category and request id, and clearly labelled
non-model answers. Patient-record findings are kept separate from phenotypes that are merely ANNOTATED to a candidate disease.
No treatment, dosage or test recommendations are generated.
"""
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.reasoning.grounding import Claim, check_claim
from src.reasoning.llm_provider import (BaseLLMProvider, InvalidModelOutput, ProviderError, ProviderTimeout, ProviderUnavailable,
                                        get_llm_provider)
from src.reasoning.llm_reasoner import LIMITATIONS

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_PROMPT = """You answer a clinician's question about ONE patient case using ONLY the numbered evidence supplied.
Each evidence line starts with a kind tag:
  PATIENT FINDING = something stated in THIS patient's record (matched to a disease annotation, or not annotated to it).
  DISEASE ANNOTATION = a phenotype the candidate DISEASE is annotated with in the knowledge base. It is NOT a finding in this patient: never say the patient has it, only that the record does not state it.
Rules:
1. Every statement cites evidence ids (e.g. "C2-E4"). A point about a candidate may cite ONLY that candidate's own ids (the prefix C<rank>-).
2. Do not add facts, genes, numbers, citations, PMIDs, DOIs or URLs that are not in the evidence.
3. Never state a definitive diagnosis (say "prioritized candidate"). Never recommend, order or advise tests, treatment, medication or next steps.
4. Scores are rank-based and uncalibrated: never call a score "high", "low" or "strong"; quote the number. You may say a rank-1 candidate has the highest final score. Population frequency is not disease probability.
5. If the evidence cannot answer the question, do NOT apologise or refuse in one line: set cannot_answer_from_evidence=true, state exactly which evidence is missing in missing_evidence, and in "answer" say what the recorded evidence DOES show (with citations).
Return valid JSON only."""

SHAPE = """{"answer": "concise answer citing ids, e.g. (C1-E2)", "answer_evidence_ids": ["C1-E2"],
 "evidence_points": [{"candidate_id": "<candidate_id exactly as given>", "text": "...", "evidence_ids": ["C1-E3"]}],
 "referenced_candidates": ["candidate names"], "cannot_answer_from_evidence": false, "missing_evidence": []}"""

KIND = {"phenotype_match": "PATIENT FINDING (matched to the disease annotation)", "patient_phenotype_not_annotated": "PATIENT FINDING (not annotated to this disease)",
        "disease_phenotype_unverified": "DISEASE ANNOTATION (not stated for this patient)", "disease_phenotypes_unavailable": "DISEASE ANNOTATION (unavailable)"}

_SCOPE = re.compile(r"\b(tests?|testing|work-?up|confirmatory|molecular|sequenc\w*|panel|treat\w*|therap\w*|medicat\w*|dos(?:e|age)|prescrib\w*|manag\w*|next steps?)\b", re.I)
_REFUSAL = re.compile(r"\b(i'?m sorry|i am sorry|cannot provide|can'?t provide|unable to (?:answer|provide)|cannot answer)\b", re.I)
_SMALLTALK = re.compile(r"^\W*(?:hi+|hello+|hey+|hola|namaste|thanks?|thank you|ok(?:ay)?|good (?:morning|afternoon|evening)|test(?:ing)?)\W*$", re.I)
_PHENO_Q = re.compile(r"phenotype|symptom|missing|unverified|absent|distinguish|feature|annotat", re.I)
RETRYABLE = {"rate_limited", "timeout", "provider_unavailable", "invalid_output", "model_refusal"}


class CopilotPoint(BaseModel):
    candidate_id: str
    text: str
    evidence_ids: List[str] = Field(default_factory=list)


class CopilotAnswer(BaseModel):
    answer: str
    answer_evidence_ids: List[str] = Field(default_factory=list)
    evidence_points: List[CopilotPoint] = Field(default_factory=list)
    referenced_candidates: List[str] = Field(default_factory=list)
    cannot_answer_from_evidence: bool = False
    missing_evidence: List[str] = Field(default_factory=list)


def merge_packets(packets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"evidence": [e for p in packets for e in p["evidence"]], "genes": sorted({g for p in packets for g in p.get("genes", [])})}


class DoctorCopilot:
    def __init__(self, config: Dict[str, Any], provider: Optional[BaseLLMProvider] = None):
        self.config = config
        self.provider = provider or get_llm_provider(config)
        self.max_attempts = int(config.get("reasoning", {}).get("max_attempts", 2))

    # ---- prompt -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _prompt(query: str, clinical_text: str, packets: List[Dict[str, Any]], errors: Optional[List[str]] = None) -> str:
        blocks = []
        for pk in packets:
            ev = "\n".join(f"  [{e['id']}] {KIND.get(e['type'], e['type'].upper())}: {e['text']}" for e in pk["evidence"])
            blocks.append(f"CANDIDATE candidate_id=\"{pk['candidate_id']}\" name=\"{pk['disease_name']}\" rank={pk['rank']} "
                          f"(cite only ids starting C{pk['rank']}-)\n{ev}")
        retry = ("\nYour previous answer was rejected: " + "; ".join(errors[:5]) + ". Fix these problems without weakening the rules.\n") if errors else ""
        return (f"=== PATIENT NARRATIVE (the only source of patient findings) ===\n{clinical_text}\n\n=== CANDIDATES AND NUMBERED EVIDENCE ===\n" + "\n\n".join(blocks) +
                f"\n\n=== CLINICIAN QUESTION ===\n{query}\n{retry}\nReturn JSON in this shape:\n{SHAPE}\n")

    # ---- deterministic pieces -----------------------------------------------------------------------------------------
    @staticmethod
    def annotations_not_in_record(packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Phenotypes ANNOTATED to a candidate disease that the patient record does not state. Never patient findings."""
        out = []
        for p in packets[:3]:
            for e in p["evidence"]:
                if e["type"] == "disease_phenotype_unverified":
                    out.append({"candidate": p["disease_name"], "candidate_id": p["candidate_id"], "disease_annotations_not_stated_in_record": e["data"].get("names", []),
                                "evidence_id": e["id"], "kind": "candidate_disease_annotation_not_patient_finding",
                                "note": "These are phenotypes the DISEASE is annotated with. They are not findings in this patient and their absence is not established."})
        return out

    @staticmethod
    def patient_findings(case_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"hpo_id": h.get("hpo_id"), "name": h.get("name"), "mention": h.get("mention"), "kind": "patient_record_finding"}
                for h in case_context.get("hpo_terms", []) if h.get("hpo_id")]

    @staticmethod
    def _relevant(packets: List[Dict[str, Any]], q: str) -> List[Dict[str, Any]]:
        top = packets[0]
        if re.search(r"gene|genetic|variant|test|molecular|sequenc", q):
            keep = ("gene_association", "gene_association_unavailable", "variant_evidence_unavailable")
        elif re.search(r"population|indian|frequency|gnomad|indigen|south asian", q):
            keep = ("population_evidence", "population_unavailable")
        elif re.search(r"phenotype|symptom|missing|unverified|absent|distinguish", q):
            keep = ("phenotype_match", "disease_phenotype_unverified", "patient_phenotype_not_annotated")
        else:
            keep = ("retrieval", "phenotype_match", "score_breakdown")
        return [{"text": e["text"], "evidence_ids": [e["id"]]} for e in top["evidence"] if e["type"] in keep]

    def _summary(self, query: str, packets: List[Dict[str, Any]], case_context: Dict[str, Any], status: str, reason: str, category: str,
                 request_id: str, attempts: int, generated_by: str, answer: str, missing: Optional[List[str]] = None, fallback: bool = True,
                 points: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        q = query.lower()
        pts = points if points is not None else (self._relevant(packets, q) if packets else [])
        src = {e["id"]: e["source"] for p in packets for e in p["evidence"]}
        show_ann = bool(_PHENO_Q.search(q))
        return {"answer": answer, "answer_evidence_ids": [], "evidence_points": pts,
                "referenced_candidates": [packets[0]["disease_name"]] if packets else [], "cannot_answer_from_evidence": bool(missing),
                "missing_evidence": missing or [], "source_references": [{"evidence_id": i, "source": src[i]} for k in pts for i in k["evidence_ids"] if i in src],
                "provider": {"name": "llm", "model": getattr(self.provider, "model", None), "status": status, "attempts": attempts, "fallback": fallback,
                             "reason": reason, "retryable": status in RETRYABLE or category in RETRYABLE},
                "failure_category": category, "request_id": request_id, "generated_by": generated_by, "fallback": fallback,
                "patient_record_findings": self.patient_findings(case_context),
                "candidate_annotations_not_in_record": self.annotations_not_in_record(packets) if show_ann else [],
                "areas_to_verify": self.annotations_not_in_record(packets) if show_ann else [], "limitations": LIMITATIONS}

    def _scope_answer(self, query, packets, case_context, rid):
        top = packets[0]
        genes = {p["disease_name"]: p.get("genes", []) for p in packets[:3]}
        gene_txt = "; ".join(f"{n}: {', '.join(g) if g else 'no gene association recorded'}" for n, g in genes.items())
        answer = ("This tool describes recorded evidence; it does not recommend tests, treatment or next steps, and no variant evidence exists for this patient. "
                  f"What the knowledge base records for the top candidates — {gene_txt}. Variant-level and patient genotype evidence is unavailable, so no genetic conclusion can be drawn.")
        return self._summary(query, packets, case_context, "scope_limited", "question asks for test/management advice", "out_of_scope", rid, 0, "evidence_summary",
                             answer, missing=["patient genotype / variant evidence", "clinician judgement on testing"], fallback=False)

    # ---- fallback ------------------------------------------------------------------------------------------------------
    def _fallback(self, query, packets, case_context, status, reason, rid, category, attempts=0):
        top = packets[0] if packets else None
        answer = (f"Deterministic fallback (no language model was used). Evidence recorded for the top prioritized candidate '{top['disease_name']}':"
                  if top else "No candidate evidence is available for this case.")
        return self._summary(query, packets, case_context, status, reason, category, rid, attempts, "deterministic_fallback", answer)

    # ---- main ------------------------------------------------------------------------------------------------------------
    def answer_query(self, query: str, case_context: Dict[str, Any]) -> Dict[str, Any]:
        rid = uuid.uuid4().hex[:10]
        t0 = time.time()
        res = self._answer(query, case_context, rid)
        logger.info("copilot req=%s status=%s category=%s generated_by=%s attempts=%s ms=%d", rid, res["provider"]["status"], res.get("failure_category"),
                    res["generated_by"], res["provider"].get("attempts"), (time.time() - t0) * 1000)
        return res

    def _answer(self, query: str, case_context: Dict[str, Any], rid: str) -> Dict[str, Any]:
        packets = [c["packet"] for c in case_context.get("fused_candidates", [])[:5] if c.get("packet")][:3]   # smaller prompt: provider token-per-minute limit
        clinical_text = case_context.get("clinical_text", "")
        if not packets:
            r = self._fallback(query, [], case_context, "no_case_context", "No analysed case / candidate evidence is available.", rid, "no_case_context")
            r["answer"] = "No analysed case is available, so there is no evidence to answer from. Run a diagnosis first."
            r["provider"]["retryable"] = False
            return r
        if _SMALLTALK.match(query) or len(re.findall(r"[A-Za-z]{2,}", query)) < 2:
            r = self._summary(query, packets, case_context, "not_applicable", "greeting or no question; no model call made", "no_question", rid, 0, "assistant_notice",
                              "Hello. Please ask a question about this case, for example why the top candidate was prioritized, which of the patient's phenotypes match it, "
                              "or what evidence is missing. I answer only from the recorded case evidence.", fallback=False, points=[])
            r["provider"]["retryable"] = False
            r["candidate_annotations_not_in_record"] = r["areas_to_verify"] = []
            return r
        if _SCOPE.search(query):
            return self._scope_answer(query, packets, case_context, rid)
        health = self.provider.check_health()
        if health.get("status") != "healthy":
            st = "provider_unavailable" if health.get("status") == "offline" else health.get("status")
            return self._fallback(query, packets, case_context, st, f"Language-model health check: {health.get('status')}", rid, st if st.startswith("provider") else f"provider_{st}")
        by_cand = {p["candidate_id"]: p for p in packets}
        merged = merge_packets(packets)
        errors: List[str] = []
        t0 = time.time()
        last_category = "invalid_output"
        for attempt in range(1, self.max_attempts + 1):
            try:
                data, _ = self.provider.generate_json_with_meta(self._prompt(query, clinical_text, packets, errors), COPILOT_SYSTEM_PROMPT)
            except ProviderTimeout as e:
                return self._fallback(query, packets, case_context, "timeout", str(e), rid, "provider_timeout", attempt)
            except ProviderUnavailable as e:
                r = self._fallback(query, packets, case_context, e.status, str(e), rid, e.status if e.status.startswith("provider") else f"provider_{e.status}", attempt)
                if getattr(e, "retry_after", None):
                    r["provider"]["retry_after_seconds"] = int(e.retry_after)
                if getattr(e, "limit", None):
                    r["provider"]["limit"] = e.limit
                return r
            except InvalidModelOutput as e:
                errors, last_category = [f"invalid_output: {e}"], "malformed_output"
                continue
            except ProviderError as e:
                return self._fallback(query, packets, case_context, e.status, str(e), rid, e.status if e.status.startswith("provider") else f"provider_{e.status}", attempt)
            try:
                ans = CopilotAnswer(**data)
            except ValidationError as e:
                errors, last_category = [f"schema: {'.'.join(map(str, err['loc']))} {err['msg']}" for err in e.errors()[:4]], "schema_error"
                continue
            refusal = bool(_REFUSAL.search(ans.answer)) or (ans.cannot_answer_from_evidence and not ans.missing_evidence)
            if refusal:
                errors, last_category = ["you refused or gave no reason; state which evidence is missing and what the recorded evidence shows, with citations"], "model_refusal"
                continue
            removed, kept = [], []
            for p in ans.evidence_points:
                pk = by_cand.get(p.candidate_id)
                r = check_claim(Claim(text=p.text, evidence_ids=p.evidence_ids), pk) if pk else "unknown_candidate"
                (removed.append({"text": p.text[:100], "reason": r}) if r else kept.append({"text": p.text, "evidence_ids": p.evidence_ids, "candidate_id": p.candidate_id}))
            a_reason = "" if (ans.cannot_answer_from_evidence and not ans.answer_evidence_ids) else check_claim(Claim(text=ans.answer, evidence_ids=ans.answer_evidence_ids), merged)
            if a_reason:
                errors, last_category = [f"answer rejected: {a_reason}"], f"grounding_rejected:{a_reason.split(':')[0]}"
                continue
            src = {e["id"]: e["source"] for e in merged["evidence"]}
            ids = list(dict.fromkeys(ans.answer_evidence_ids + [i for k in kept for i in k["evidence_ids"]]))
            show_ann = bool(_PHENO_Q.search(query))
            return {"answer": ans.answer, "answer_evidence_ids": ans.answer_evidence_ids, "evidence_points": kept,
                    "referenced_candidates": ans.referenced_candidates, "cannot_answer_from_evidence": ans.cannot_answer_from_evidence,
                    "missing_evidence": ans.missing_evidence, "source_references": [{"evidence_id": i, "source": src[i]} for i in ids if i in src],
                    "provider": {"name": "llm", "model": getattr(self.provider, "model", None), "status": "ok", "attempts": attempt,
                                 "latency_ms": round((time.time() - t0) * 1000, 1), "fallback": False, "retryable": False,
                                 "grounding": {"points_kept": len(kept), "points_removed": len(removed), "removed": removed}},
                    "failure_category": "none", "request_id": rid, "generated_by": "language_model", "fallback": False,
                    "patient_record_findings": self.patient_findings(case_context),
                    "candidate_annotations_not_in_record": self.annotations_not_in_record(packets) if show_ann else [],
                    "areas_to_verify": self.annotations_not_in_record(packets) if show_ann else [], "limitations": LIMITATIONS}
        # attempts exhausted: informative, validated, clearly labelled answer built from the evidence (never a bare apology)
        if last_category == "model_refusal":
            return self._summary(query, packets, case_context, "ok", "model did not give a usable answer; evidence summary shown", last_category, rid, self.max_attempts,
                                 "evidence_summary", "The model could not give a grounded answer to this question. The evidence recorded for the top prioritized candidate is shown instead.",
                                 missing=["a grounded model answer"], fallback=True)
        return self._fallback(query, packets, case_context, "invalid_output", "; ".join(errors[:3]) or "model output failed validation", rid, last_category, self.max_attempts)
