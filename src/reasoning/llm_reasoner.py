"""Evidence-grounded explanations from the configured language model (Groq is the only provider).

One structured request covers all candidates. The model only sees the evidence packets (each fact has an id such as C1-E3);
it must cite those ids. Output is schema-validated and grounding-checked (grounding.py); unsupported claims are removed and
counted. Invalid output is retried a bounded number of times with the validation errors fed back. If the language model is unavailable,
times out or keeps returning invalid output, the response says so explicitly (`provider.status`, `fallback: true`) and a
deterministic explanation built verbatim from the evidence is returned, labelled as a fallback. A fallback is never
presented as an LLM result and no LLM result is ever fabricated.
"""
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.reasoning.grounding import CLAIM_FIELDS, parse_batch, validate_and_filter
from src.reasoning.llm_provider import (BaseLLMProvider, InvalidModelOutput, ProviderTimeout, ProviderUnavailable,
                                        get_llm_provider)

logger = logging.getLogger(__name__)

LIMITATIONS = [
    "Research decision-support prototype; not a diagnosis and not a substitute for qualified clinical interpretation.",
    "Scores are retrieval/ranking scores, not probabilities. Absence of evidence in this system does not establish absence of disease.",
    "Population allele frequency is evidence about occurrence in a population, not a disease probability.",
    "Literature evidence was not assessed.",
]

SYSTEM_PROMPT = """You explain why candidate rare diseases were prioritised for a patient, using ONLY the numbered evidence supplied.
Rules:
1. Every claim must cite one or more evidence ids (for example "C1-E3") copied exactly from the evidence list of the SAME candidate.
2. Do not add facts, genes, phenotypes, numbers, citations, PMIDs, DOIs or URLs that are not in the evidence. If something is unknown, say it is unavailable.
3. Never state or imply a definitive diagnosis. Never give treatment, medication or dosage advice.
4. Scores are not probabilities and are not calibrated: never call a score "high", "low" or "strong"; quote the number instead. Population frequency is not disease probability. A phenotype that is merely not stated is "unverified", not absent.
5. Return valid JSON only, exactly in the requested structure. Cite evidence ids INLINE in the text, in parentheses, e.g. (C1-E2); do not output separate id lists. Output compact JSON without extra whitespace."""

# The model is asked for SHORT text only (generation on the target machine is ~5-11 tokens/s). The structured evidence sections
# (supporting / unverified / contradictory / genetic / population) are filled verbatim from the knowledge-base evidence by the
# backend, so they are grounded by construction and cost no tokens.
JSON_SHAPE = """{"candidates":[{"candidate_id":"<exactly as given>","summary":"<=50 words, cite evidence inline like (C1-E2)","ranking_note":"<=25 words: quote THIS candidate's own rank and score numbers, cite only THIS candidate's own evidence ids; never cite another candidate's ids","uncertainties":["<=20 words, cite inline"]}]}"""


def _provider_block(provider, status, attempts=0, latency_ms=None, fallback=False, reason=None, grounding=None):
    return {"name": "llm", "model": getattr(provider, "model", None), "status": status, "attempts": attempts,
            "latency_ms": latency_ms, "fallback": fallback, "reason": reason, "grounding": grounding}


class LLMReasoner:
    def __init__(self, config: Dict[str, Any], provider: Optional[BaseLLMProvider] = None):
        self.config = config
        self.provider = provider or get_llm_provider(config)
        self.max_attempts = int(config.get("reasoning", {}).get("max_attempts", 2))
        self.cache: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def _prompt(clinical_text: str, packets: List[Dict[str, Any]], errors: Optional[List[str]] = None) -> str:
        blocks = []
        for pk in packets:
            ev = "\n".join(f"  [{e['id']}] ({e['type']}) {e['text']}  <source: {e['source']}>" for e in pk["evidence"])
            blocks.append(f"CANDIDATE candidate_id=\"{pk['candidate_id']}\" name=\"{pk['disease_name']}\" rank={pk['rank']} "
                          f"evidence_label=\"{pk['labels']['label']}\" evidence_completeness={pk['completeness']['fraction']}\n{ev}")
        retry = ("\nYour previous answer was rejected: " + "; ".join(errors[:6]) + ". Fix these problems.\n") if errors else ""
        return (f"=== PATIENT NARRATIVE ===\n{clinical_text}\n\n=== CANDIDATES AND NUMBERED EVIDENCE ===\n" + "\n\n".join(blocks) +
                f"\n\n=== TASK ===\nFor EACH candidate write the short explanation fields. Use only the evidence above, cite ids, and respect the word limits.{retry}\n"
                f"Return JSON in exactly this shape:\n{JSON_SHAPE}\n")

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def deterministic_fallback(pk: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Built verbatim from the evidence items - grounded by construction, labelled as a fallback."""
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for e in pk["evidence"]:
            by_type.setdefault(e["type"], []).append(e)

        def claims(*types):
            return [{"text": e["text"], "evidence_ids": [e["id"]]} for t in types for e in by_type.get(t, [])]

        retr = (by_type.get("retrieval") or [None])[0]
        sb = (by_type.get("score_breakdown") or [None])[0]
        summary = (f"{pk['disease_name']} is ranked #{pk['rank']}. Evidence label: {pk['labels']['label']} "
                   f"(matched fraction {pk['labels']['matched_fraction']}). See the score breakdown for the exact components.")
        return {
            "candidate_id": pk["candidate_id"], "summary": summary,
            "summary_evidence_ids": [e["id"] for e in (retr, sb) if e],
            "supporting_evidence": claims("phenotype_match"),
            "missing_or_unverified_evidence": claims("patient_phenotype_not_annotated", "disease_phenotype_unverified", "disease_phenotypes_unavailable"),
            "contradictory_evidence": claims("contradiction"),
            "genetic_evidence": claims("gene_association", "gene_association_unavailable", "variant_evidence_unavailable"),
            "population_evidence": claims("population_evidence", "population_unavailable"),
            "uncertainties": [{"text": e["text"], "evidence_ids": [e["id"]]} for e in (retr, sb) if e],
            "generated_by": "deterministic_fallback", "fallback": True, "fallback_reason": reason,
        }

    def _finalize(self, expl: Dict[str, Any], pk: Dict[str, Any], provider_status: str, generated_by: str) -> Dict[str, Any]:
        src = {e["id"]: e["source"] for e in pk["evidence"]}
        used: List[str] = []
        if expl.get("ranking_note"):
            expl["ranking_note_evidence_ids"] = expl["ranking_note"]["evidence_ids"]
        for f in ["summary_evidence_ids", "ranking_note_evidence_ids"] + CLAIM_FIELDS:
            vals = expl.get(f, [])
            ids = vals if f.endswith("evidence_ids") else [i for c in vals for i in c["evidence_ids"]]
            for i in ids:
                if i not in used:
                    used.append(i)
        expl.update({
            "disease_name": pk["disease_name"], "rank": pk["rank"],
            "source_references": [{"evidence_id": i, "source": src[i]} for i in used if i in src],
            "provider_status": provider_status, "generated_by": generated_by, "limitations": LIMITATIONS,
            "evidence_label": pk["labels"]["label"], "evidence_completeness": pk["completeness"]["fraction"], "calibrated_confidence": None,
        })
        expl["fallback"] = generated_by != "language_model"
        return expl

    # ---------------------------------------------------------------------------------------------
    def explain_candidates(self, clinical_text: str, packets: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not packets:
            return {"provider": _provider_block(self.provider, "no_candidates"), "candidates": []}
        key = hashlib.sha256((json.dumps([p["evidence"] for p in packets], sort_keys=True, default=str) + clinical_text
                              + str(getattr(self.provider, "model", ""))).encode()).hexdigest()
        if key in self.cache:
            cached = json.loads(json.dumps(self.cache[key]))
            cached["provider"]["cached"] = True
            return cached
        by_id = {p["candidate_id"]: p for p in packets}
        health = self.provider.check_health()
        if health.get("status") != "healthy":
            status = "provider_unavailable" if health.get("status") == "offline" else health.get("status", "provider_unavailable")
            return self._all_fallback(packets, status, f"Language-model health check: {health.get('status')}"
                                      + (f" ({health.get('error')})" if health.get("error") else ""))
        errors: List[str] = []
        retry_log: List[str] = []
        t0 = time.time()
        for attempt in range(1, self.max_attempts + 1):
            retry_log.extend(errors)
            try:
                data, _ = self.provider.generate_json_with_meta(self._prompt(clinical_text, packets, errors), SYSTEM_PROMPT)
            except ProviderTimeout as e:
                return self._all_fallback(packets, "timeout", str(e), attempts=attempt, started=t0)
            except ProviderUnavailable as e:                      # not_configured / auth_error / model_unavailable / rate_limited / provider_unavailable
                return self._all_fallback(packets, e.status, str(e), attempts=attempt, started=t0)
            except InvalidModelOutput as e:
                errors = [f"invalid_output: {e}"]
                logger.warning("LLM invalid output (attempt %d): %s", attempt, e)
                continue
            batch, schema_errors = parse_batch(data)
            if batch is None:
                errors = schema_errors
                continue
            filtered, stats = validate_and_filter(batch, by_id)
            if not filtered:
                errors = ["no candidate in the answer matched the supplied candidate_ids exactly"]
                continue
            missing = [cid for cid in by_id if cid not in filtered]
            out_cands = []
            for pk in sorted(packets, key=lambda p: p["rank"]):
                e = filtered.get(pk["candidate_id"])
                if e is None:
                    out_cands.append(self._finalize(self.deterministic_fallback(pk, "model omitted this candidate"), pk, "partial_fallback", "deterministic_fallback"))
                    continue
                base = self.deterministic_fallback(pk, "")
                merged = {k: base[k] for k in CLAIM_FIELDS}                      # evidence sections: verbatim from the knowledge base
                merged["uncertainties"] = list(e.get("uncertainties") or []) + base["uncertainties"]
                merged.update(candidate_id=pk["candidate_id"], summary=e.get("summary"), summary_evidence_ids=e.get("summary_evidence_ids", []),
                              ranking_note=e.get("ranking_note"))
                if not merged["summary"]:
                    merged["summary"], merged["summary_evidence_ids"] = base["summary"], base["summary_evidence_ids"]
                    merged["summary_note"] = "model summary removed by the grounding check; deterministic summary shown"
                merged["evidence_sections_source"] = "knowledge-base evidence, verbatim"
                out_cands.append(self._finalize(merged, pk, "ok", "language_model"))
            result = {"provider": _provider_block(self.provider, "ok" if not missing else "partial", attempt, round((time.time() - t0) * 1000, 1), False,
                                                  None if not missing else f"model omitted: {missing}", {**stats, "retry_reasons": retry_log}),
                      "candidates": out_cands}
            if not missing:
                self.cache[key] = result
            return result
        return self._all_fallback(packets, "invalid_output", "; ".join(errors[:4]) or "model output failed validation",
                                  attempts=self.max_attempts, started=t0)

    def _all_fallback(self, packets, status, reason, attempts=0, started=None):
        cands = [self._finalize(self.deterministic_fallback(pk, reason), pk, status, "deterministic_fallback")
                 for pk in sorted(packets, key=lambda p: p["rank"])]
        return {"provider": _provider_block(self.provider, status, attempts, round((time.time() - started) * 1000, 1) if started else None, True, reason),
                "candidates": cands}

    # ---- legacy single-candidate wrapper (existing /api/explain contract) --------------------------
    def explain_candidate(self, candidate_evidence: Dict[str, Any], clinical_case_text: str) -> Dict[str, Any]:
        pk = candidate_evidence.get("packet")
        if pk is None:
            raise ValueError("candidate_evidence must be a fused candidate containing an evidence packet")
        res = self.explain_candidates(clinical_case_text, [pk])
        out = res["candidates"][0]
        out["provider"] = res["provider"]
        return out
