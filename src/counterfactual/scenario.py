"""Phase 5R counterfactual scenarios.

A scenario is an ordered list of operations (add / remove / modify) applied to a COPY of the baseline phenotype set. The hypothetical
set is run through the existing ranking pipeline (`run_from_hpo_terms`) exactly like the baseline, so differences come only from the
phenotype input. Nothing is hard-coded, no score is edited, no HPO id is invented, and the stored case is never mutated.

Conventions (documented in the Phase 5R report):
* rank displacement = baseline_rank - counterfactual_rank  (positive = moved UP the list, negative = moved DOWN)
* ranks are computed over the top `compare_depth` candidates of each run; "absent" means not in that depth (not "ruled out")
* magnitude rule: |displacement| >= 3, or entering/leaving the displayed top-k  -> "substantial"; 1-2 -> "small"; 0 -> "unchanged"
"""
import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

HPO_RE = re.compile(r"^HP:\d{7}$", re.I)
OK_STATUSES = ("exact", "synonym", "lexical", "semantic")
SCENARIO_LABEL = "HYPOTHETICAL SCENARIO — not an observed clinical finding"
RANK_RULE = "rank displacement = baseline_rank − counterfactual_rank; positive means the candidate moved up the list."
MAGNITUDE_RULE = ("substantial: |displacement| ≥ 3, or the candidate entered/left the list at a rank within the displayed top-k; small: |displacement| 1–2, or entered/left the list only beyond the displayed top-k; "
                  "unchanged: 0. A descriptive threshold, not a statistical or clinical one.")
DISCLAIMER = ("Computational sensitivity analysis on a hypothetical phenotype set. It does not establish, support or exclude any real "
              "diagnosis, and ranking changes are not causal or diagnostic evidence.")


def resolve_phenotype(normalizer, query: str) -> Dict[str, Any]:
    """Resolve free text or an HPO id to ONE valid HPO term, or report why not. Never invents an id."""
    q = (query or "").strip()
    if not q:
        return {"input": query, "status": "invalid", "reason": "empty phenotype", "hpo_id": None}
    if HPO_RE.match(q):
        hid = normalizer.res.resolve_id(q.upper())
        if hid is None:
            return {"input": q, "status": "invalid", "reason": "not a known HPO term", "hpo_id": None}
        if not normalizer.res.is_phenotypic(hid):
            return {"input": q, "status": "invalid", "reason": "HPO term is not a phenotypic abnormality", "hpo_id": hid, "name": normalizer._name(hid)}
        return {"input": q, "status": "resolved", "hpo_id": hid, "name": normalizer._name(hid), "score": 1.0, "matching_method": "hpo_id", "confidence": "exact id"}
    r = normalizer.normalize_detailed(q)
    if r["status"] in OK_STATUSES:
        if not r.get("is_phenotypic", True):
            return {"input": q, "status": "invalid", "reason": "maps to a non-phenotype (modifier) HPO term", "hpo_id": r["hpo_id"], "name": r["term"]}
        return {"input": q, "status": "resolved", "hpo_id": r["hpo_id"], "name": r["term"], "score": r["score"],
                "matching_method": r["matching_method"], "confidence": r["status"]}
    if r["status"] == "ambiguous":
        return {"input": q, "status": "ambiguous", "hpo_id": None, "suggestions": r.get("candidates", [])}
    return {"input": q, "status": "unresolved", "hpo_id": None, "suggestions": r.get("suggestions", [])}


def _term(res: Dict[str, Any], origin: str) -> Dict[str, Any]:
    return {"hpo_id": res["hpo_id"], "name": res["name"], "score": res.get("score"), "matching_method": res.get("matching_method"),
            "status": res.get("confidence"), "origin": origin}


def _match(terms: List[Dict[str, Any]], key: str, normalizer) -> Optional[int]:
    k = (key or "").strip().lower()
    for i, t in enumerate(terms):
        if t["hpo_id"].lower() == k or (t.get("name") or "").lower() == k:
            return i
    if k and not HPO_RE.match(k):
        r = normalizer.normalize_detailed(key)
        if r["status"] in OK_STATUSES:
            for i, t in enumerate(terms):
                if t["hpo_id"] == r["hpo_id"]:
                    return i
    return None


def apply_operations(baseline: List[Dict[str, Any]], operations: List[Dict[str, Any]], normalizer):
    """Returns (hypothetical_terms, op_log). Baseline is deep-copied and never mutated."""
    terms = [dict(copy.deepcopy(t), origin="observed") for t in baseline if t.get("hpo_id")]
    log = []
    for n, op in enumerate(operations, 1):
        kind = (op.get("op") or op.get("operation") or "").lower()
        rec: Dict[str, Any] = {"step": n, "op": kind, "input": op.get("phenotype"), "applied": False}
        if kind == "add":
            r = resolve_phenotype(normalizer, op.get("phenotype", ""))
            rec["resolution"] = r
            if r["status"] != "resolved":
                rec["status"] = r["status"]
            elif any(t["hpo_id"] == r["hpo_id"] for t in terms):
                rec["status"] = "already_present"
            else:
                terms.append(_term(r, "hypothetical_added"))
                rec.update(applied=True, status="applied")
        elif kind == "remove":
            i = _match(terms, op.get("phenotype", ""), normalizer)
            if i is None:
                rec["status"] = "not_in_case"
            else:
                rec["removed"] = {"hpo_id": terms[i]["hpo_id"], "name": terms[i]["name"], "origin": terms[i]["origin"]}
                terms.pop(i)
                rec.update(applied=True, status="applied")
        elif kind == "modify":
            i = _match(terms, op.get("phenotype", ""), normalizer)
            r = resolve_phenotype(normalizer, op.get("replacement", ""))
            rec["resolution"] = r
            rec["replacement_input"] = op.get("replacement")
            if i is None:
                rec["status"] = "not_in_case"
            elif r["status"] != "resolved":
                rec["status"] = r["status"]
            elif any(t["hpo_id"] == r["hpo_id"] for j, t in enumerate(terms) if j != i):
                rec["status"] = "replacement_already_present"
            else:
                rec["original"] = {"hpo_id": terms[i]["hpo_id"], "name": terms[i]["name"], "origin": terms[i]["origin"]}
                terms[i] = _term(r, "hypothetical_modified")
                terms[i]["replaces"] = rec["original"]
                rec.update(applied=True, status="applied")
        else:
            rec["status"] = "invalid_operation"
        log.append(rec)
    return terms, log


def _row(c: Optional[Dict[str, Any]], rank: Optional[int]) -> Dict[str, Any]:
    if c is None:
        return {"present": False, "rank": None, "retrieval_score": None, "phenotype_score": None, "base_score": None,
                "population_contribution": None, "final_score": None}
    return {"present": True, "rank": rank, "retrieval_score": c.get("retrieval_score"), "phenotype_score": c.get("phenotype_score"),
            "base_score": c.get("base_score"), "population_contribution": c.get("population_contribution"), "final_score": c.get("final_score")}


def _diff(a, b):
    return None if a is None or b is None else round(b - a, 6)


def compare_rankings(baseline: List[Dict[str, Any]], scenario: List[Dict[str, Any]], display_k: int) -> List[Dict[str, Any]]:
    bmap = {c["disease_id"]: (i + 1, c) for i, c in enumerate(baseline)}
    smap = {c["disease_id"]: (i + 1, c) for i, c in enumerate(scenario)}
    out = []
    for did in list(dict.fromkeys([c["disease_id"] for c in baseline] + [c["disease_id"] for c in scenario])):
        br, bc = bmap.get(did, (None, None))
        sr, sc = smap.get(did, (None, None))
        b, s = _row(bc, br), _row(sc, sr)
        name = (bc or sc).get("disease_name")
        if br and sr:
            disp = br - sr
            presence = "both"
        else:
            disp = None
            presence = "left_list" if br else "entered_list"
        in_b, in_s = bool(br and br <= display_k), bool(sr and sr <= display_k)
        if disp is None:
            mag = "substantial" if (br or sr) <= display_k else "small"     # entered/left the list: substantial only if within the displayed top-k
        elif in_b != in_s or abs(disp) >= 3:
            mag = "substantial"
        elif abs(disp) >= 1:
            mag = "small"
        else:
            mag = "unchanged"
        out.append({"disease_id": did, "disease_name": name, "presence": presence, "baseline": b, "counterfactual": s,
                    "rank_displacement": disp,
                    "direction": None if disp is None else ("up" if disp > 0 else "down" if disp < 0 else "unchanged"),
                    "magnitude": mag,
                    "entered_top_k": (not in_b) and in_s, "left_top_k": in_b and (not in_s),
                    "deltas": {k: _diff(b[k], s[k]) for k in ("retrieval_score", "phenotype_score", "base_score", "population_contribution", "final_score")}})
    out.sort(key=lambda r: (r["counterfactual"]["rank"] is None, r["counterfactual"]["rank"] or 0, r["baseline"]["rank"] or 0))
    return out


def explain_changes(op_log, deltas, display_k, w_population, base_terms, hyp_terms) -> List[str]:
    """Statements derived ONLY from the computed values above."""
    msgs = []
    for r in op_log:
        if r["applied"]:
            if r["op"] == "add":
                msgs.append(f"Hypothetical addition: {r['resolution']['name']} ({r['resolution']['hpo_id']}), resolved by {r['resolution']['matching_method']} (score {r['resolution'].get('score')}).")
            elif r["op"] == "remove":
                msgs.append(f"Hypothetical removal: {r['removed']['name']} ({r['removed']['hpo_id']}) from the phenotype set.")
            elif r["op"] == "modify":
                msgs.append(f"Hypothetical modification: {r['original']['name']} ({r['original']['hpo_id']}) replaced by {r['resolution']['name']} ({r['resolution']['hpo_id']}).")
        else:
            msgs.append(f"Step {r['step']} ({r['op']} '{r.get('input') or r.get('replacement_input') or ''}') was NOT applied: {r['status']}.")
    moved = [d for d in deltas if d["rank_displacement"]]
    for d in moved[:8]:
        word = "up" if d["rank_displacement"] > 0 else "down"
        msgs.append(f"Under this hypothetical phenotype configuration, {d['disease_name']} moved {word} from rank {d['baseline']['rank']} to rank {d['counterfactual']['rank']} "
                    f"({abs(d['rank_displacement'])} position(s)); retrieval score {d['baseline']['retrieval_score']} → {d['counterfactual']['retrieval_score']}.")
    for d in deltas:
        if d["presence"] == "entered_list":
            msgs.append(f"{d['disease_name']} entered the compared list at rank {d['counterfactual']['rank']}; it was not in the baseline list (no baseline score exists).")
        elif d["presence"] == "left_list":
            msgs.append(f"{d['disease_name']} (baseline rank {d['baseline']['rank']}) is not in the scenario list; this is not an exclusion of the disease.")
    if not moved and all(d["presence"] == "both" for d in deltas):
        msgs.append("The ranking order did not change under this scenario.")
    if not w_population:
        msgs.append("The configured population weight is 0, so population evidence did not influence any ranking in this scenario or the baseline.")
    msgs.append("Information that remains unknown: the true clinical status of every hypothetical phenotype; IndiGen population data are unavailable.")
    return msgs


def run_scenario(ranking_pipeline, normalizer, baseline_terms: List[Dict[str, Any]], operations: List[Dict[str, Any]], top_k: int = 5,
                 exp_config: str = "rag_south_asian_global", compare_depth: int = 10,
                 evidence_fn: Optional[Callable[[List[Dict[str, Any]], List[Dict[str, Any]], int], List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    depth = max(compare_depth, top_k)
    base_in = copy.deepcopy(baseline_terms)
    hyp, op_log = apply_operations(base_in, operations, normalizer)
    # identical code path for both runs
    p_base = ranking_pipeline.run_from_hpo_terms(copy.deepcopy(base_in), top_k_disease=depth, exp_config=exp_config) if base_in else {"ranked_candidates": []}
    p_hyp = ranking_pipeline.run_from_hpo_terms(copy.deepcopy(hyp), top_k_disease=depth, exp_config=exp_config) if hyp else {"ranked_candidates": []}
    base_r, hyp_r = p_base["ranked_candidates"], p_hyp["ranked_candidates"]
    deltas = compare_rankings(base_r, hyp_r, top_k)
    w_pop = getattr(getattr(ranking_pipeline, "disease_ranker", None), "weights", {}).get("w_population")
    evidence = None
    if evidence_fn is not None:
        fb = {f["disease_id"]: f for f in evidence_fn(base_r[:top_k], base_in, top_k)} if base_r else {}
        fh = {f["disease_id"]: f for f in evidence_fn(hyp_r[:top_k], hyp, top_k)} if hyp_r else {}
        evidence = {}
        for did in set(fb) | set(fh):
            b, h = fb.get(did), fh.get(did)
            mb = {m["hpo_id"] for m in (b or {}).get("phenotype_evidence", {}).get("matched_phenotypes", [])}
            mh = {m["hpo_id"] for m in (h or {}).get("phenotype_evidence", {}).get("matched_phenotypes", [])}
            evidence[did] = {
                "baseline_label": (b or {}).get("labels", {}).get("label"), "counterfactual_label": (h or {}).get("labels", {}).get("label"),
                "matched_hpo_gained": sorted(mh - mb), "matched_hpo_lost": sorted(mb - mh),
                "completeness_baseline": ((b or {}).get("evidence_completeness") or {}).get("fraction"),
                "completeness_counterfactual": ((h or {}).get("evidence_completeness") or {}).get("fraction"),
                "population_status": ((h or b) or {}).get("population", {}).get("status"),
                "score_breakdown_matches_backend": all(x["score_breakdown"]["matches_backend"] for x in (b, h) if x),
                "in_displayed_top_k": {"baseline": b is not None, "counterfactual": h is not None},
            }
    applied = sum(1 for r in op_log if r["applied"])
    return {
        "scenario_id": f"scn_{uuid.uuid4().hex[:10]}", "hypothetical": True, "scenario_label": SCENARIO_LABEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_phenotypes": [dict(t) for t in base_in], "hypothetical_phenotypes": hyp, "operations": op_log,
        "operations_applied": applied, "pipeline": {"function": "Phase3RankingPipeline.run_from_hpo_terms", "exp_config": exp_config,
                                                    "compare_depth": depth, "display_top_k": top_k, "w_population": w_pop},
        "baseline_ranking": base_r[:top_k], "counterfactual_ranking": hyp_r[:top_k], "comparison": deltas, "evidence_changes": evidence,
        "explanations": explain_changes(op_log, deltas, top_k, w_pop, base_in, hyp),
        "rank_displacement_convention": RANK_RULE, "magnitude_rule": MAGNITUDE_RULE,
        "population_note": ("IndiGen is unavailable; gnomAD South Asian is reported separately; population weight is "
                            f"{w_pop}, so it {'did not change' if not w_pop else 'contributes to'} the ranking."),
        "disclaimer": DISCLAIMER,
        "status": "ok" if applied or not operations else "no_operation_applied",
    }
