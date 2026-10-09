"""Phase 4R evaluation on the fixed fixture case (tests/fixtures/phase4r_case.json, a saved real pipeline output).

Measures mechanical properties only (schema validity, grounding, reference validity, consistency, failure handling).
There is NO clinical-correctness metric: that would need expert-labelled cases, which this repository does not have.
Fake providers are FIXTURES and are labelled as such. Live-model numbers come from scripts/e2e_phase4r.py (reports/phase4r_e2e.json).
Usage: python scripts/evaluate_reasoning.py  ->  reports/reasoning_evaluation.json"""
import copy
import json
import os
import sys

sys.path.append(os.path.abspath("."))
sys.path.append(os.path.abspath("tests"))
import yaml

from src.reasoning.differential import DifferentialEngine
from src.reasoning.llm_provider import InvalidModelOutput, ProviderTimeout, ProviderUnavailable
from src.reasoning.llm_reasoner import LLMReasoner
from test_phase4r import FakeProvider, good_answer

CFG = yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))
FX = json.load(open("tests/fixtures/phase4r_case.json", encoding="utf-8"))
TEXT = FX["clinical_text"]
cands = FX["fused_candidates"]
packets = [c["packet"] for c in cands]
ev_text = {p["candidate_id"]: {e["id"]: e for e in p["evidence"]} for p in packets}


def run(script, health="healthy"):
    r = LLMReasoner(CFG, provider=FakeProvider(script, health=health))
    r.max_attempts = 2
    return r.explain_candidates(TEXT, copy.deepcopy(packets))


res = {"evaluation_set": "tests/fixtures/phase4r_case.json (1 case, 5 candidates; saved real pipeline output)",
       "providers": "FIXTURE fakes for failure/adversarial modes; no language-model quality is measured here", "metrics": {}}
m = res["metrics"]

ok = run([good_answer()])
claims = [c for cand in ok["candidates"] for k in ("supporting_evidence", "missing_or_unverified_evidence", "contradictory_evidence",
                                                 "genetic_evidence", "population_evidence", "uncertainties") for c in cand[k]]
valid_ids = lambda cand, ids: all(i in ev_text[cand["candidate_id"]] for i in ids)
m["json_schema_valid_candidates"] = f"{sum(1 for c in ok['candidates'] if c.get('candidate_id') and c.get('summary'))}/{len(ok['candidates'])}"
m["claims_total"] = len(claims)
m["claims_with_valid_evidence_ids"] = sum(1 for cand in ok["candidates"] for k in ("supporting_evidence", "genetic_evidence", "population_evidence")
                                          for c in cand[k] if c["evidence_ids"] and valid_ids(cand, c["evidence_ids"]))
m["reference_validity"] = all(valid_ids(cand, [r["evidence_id"]]) for cand in ok["candidates"] for r in cand["source_references"])
m["sections_verbatim_from_knowledge_base"] = all(c["text"] in {e["text"] for e in ev_text[cand["candidate_id"]].values()}
                                                 for cand in ok["candidates"] for k in ("supporting_evidence", "genetic_evidence", "population_evidence")
                                                 for c in cand[k])
m["candidate_order_matches_ranking"] = [c["candidate_id"] for c in ok["candidates"]] == [p["candidate_id"] for p in sorted(packets, key=lambda p: p["rank"])]
m["score_breakdown_matches_backend"] = all(c["score_breakdown"]["matches_backend"] for c in cands)
m["completeness_values"] = {c["disease_id"]: c["evidence_completeness"]["fraction"] for c in cands}
m["missing_data_handling"] = {c["disease_id"]: sorted(c["evidence_completeness"]["unavailable"]) for c in cands}
d = DifferentialEngine(CFG).generate_differential(copy.deepcopy(cands), TEXT)
m["differential_order_consistent"] = [t["disease_id"] for t in d["top_candidates"]] == [c["disease_id"] for c in cands]
m["differential_scores_equal_backend"] = all(abs(t["final_score"] - c["final_score"]) < 1e-5 for t, c in zip(d["top_candidates"], cands))

# adversarial: fabricated citations, unknown ids, treatment advice must be removed
bad = good_answer()
bad["candidates"][0]["summary"] = "Confirmed diagnosis; see PMID 99999999 (C1-E1)."
bad["candidates"][1]["summary"] = "Give 10 mg daily (C2-E1)."
bad["candidates"][2]["summary"] = "Matches (C3-E777)."
adv = run([bad])
m["adversarial"] = {"claims_removed": (adv["provider"].get("grounding") or {}).get("claims_removed"),
                    "fabricated_text_surviving": any(x in json.dumps(adv["candidates"]) for x in ("PMID 99999999", "10 mg", "C3-E777"))}

# failure handling
m["failure_modes"] = {}
for name, script, health in (("provider_offline", [good_answer()], "offline"), ("model_missing", [good_answer()], "model_missing"),
                             ("timeout", [ProviderTimeout("t")], "healthy"), ("connection_error", [ProviderUnavailable("u")], "healthy"),
                             ("malformed_twice", [InvalidModelOutput("x"), {"bad": 1}], "healthy")):
    o = run(script, health)
    m["failure_modes"][name] = {"status": o["provider"]["status"], "fallback_flag": o["provider"]["fallback"],
                                "all_candidates_labelled_fallback": all(c["generated_by"] == "deterministic_fallback" and c["fallback"] for c in o["candidates"]),
                                "candidates_returned": len(o["candidates"])}
m["population_provenance"] = {c["disease_id"]: {"status": c["population"]["status"], "indigen": c["population"]["indigen"]["status"],
                                                "contribution": c["population_contribution"]} for c in cands}

live = "reports/phase4r_e2e.json"
if os.path.exists(live):
    e = json.load(open(live, encoding="utf-8"))["steps"]["reason"]
    res["live_model"] = {"provider": e["provider"], "grounding": e["grounding"], "seconds": e["seconds"]}
res["limitations"] = ["No expert-labelled clinical cases exist; clinical correctness is not measured.",
                      "Single fixed case; results do not generalise across cases.",
                      "Grounding checks are lexical/structural (ids, numbers, symbols, banned wording), so a fluent but subtly misleading sentence that cites a real id could pass.",
                      "Live-model numbers (latency, claims removed) come from one run on one machine."]
json.dump(res, open("reports/reasoning_evaluation.json", "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps(m, indent=1, default=str)[:4000])
