"""Real Phase 5R end-to-end run against the running API (no fixtures).
Workflow A: unstructured note -> structured draft -> verify every fact against the input.
Workflow B: baseline -> hypothetical removal -> hypothetical addition, with real retrieval/ranking outputs.
Usage: python scripts/e2e_phase5r.py [base_url]  ->  reports/phase5r_e2e.json"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


def post(path, body, headers=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


out = {"input": TEXT}

# ---- Workflow A -------------------------------------------------------------------------------------------------------
d = post("/api/scribe/draft", {"clinical_text": TEXT})
checks = {
    "all_statements_verbatim_in_input": all(TEXT[s["source"]["start"]:s["source"]["end"]] == s["text"] for s in d["statements"] if s["source"]["start"] >= 0),
    "all_phenotype_mentions_in_input": all(TEXT[p["source"]["start"]:p["source"]["end"]] == p["mention"] for p in d["phenotypes"]),
    "sections_not_provided": [k for k, v in d["sections"].items() if v["status"] == "not_provided"],
    "sections_provided": [k for k, v in d["sections"].items() if v["status"] == "provided"],
    "saved": d["saved"], "status": d["status"], "language_model": d["provider"]["language_model"],
    "invented_fact_keywords_present": [w for w in ("male", "female", "year-old", "mri", "eeg", "consanguin", "mother", "father")
                                       if w in json.dumps([s["text"] for s in d["statements"]]).lower()],
    "diagnosis_input": d["diagnosis_input"],
}
out["workflow_a"] = {"draft_id": d["draft_id"], "checks": checks,
                     "phenotypes": [{k: p[k] for k in ("mention", "status", "hpo_id", "hpo_name", "normalization_status", "mapping_score")} for p in d["phenotypes"]],
                     "statements": [{k: s[k] for k in ("id", "text", "temporal", "contains_negation_cue", "contains_uncertainty_cue")} for s in d["statements"]],
                     "missing_information": [i["text"] for i in d["sections"]["missing_or_unverified_information"]["items"]]}
neg = post("/api/scribe/draft", {"clinical_text": "Mother reports that the child does not have seizures. Possible developmental delay; assessment pending. Seizures began around age three.", "save": False})
out["workflow_a"]["semantics_probe"] = {"statuses": [(p["mention"], p["status"]) for p in neg["phenotypes"]], "temporal": [s["temporal"] for s in neg["statements"]],
                                        "diagnosis_input": neg["diagnosis_input"]}

# ---- Workflow B -------------------------------------------------------------------------------------------------------
diag = post("/api/diagnose", {"clinical_text": TEXT, "top_k": 5})
cid = diag["case_id"]


def summarize(sc):
    return {"scenario_id": sc["scenario_id"], "label": sc["scenario_label"], "operations": sc["operations"],
            "baseline_phenotypes": [t["hpo_id"] for t in sc["baseline_phenotypes"]], "hypothetical_phenotypes": [(t["hpo_id"], t["origin"]) for t in sc["hypothetical_phenotypes"]],
            "baseline_ranking": [(i + 1, c["disease_id"], c["final_score"]) for i, c in enumerate(sc["baseline_ranking"])],
            "counterfactual_ranking": [(i + 1, c["disease_id"], c["final_score"]) for i, c in enumerate(sc["counterfactual_ranking"])],
            "comparison": [{"disease_id": r["disease_id"], "presence": r["presence"], "base_rank": r["baseline"]["rank"], "cf_rank": r["counterfactual"]["rank"],
                            "displacement": r["rank_displacement"], "magnitude": r["magnitude"], "deltas": r["deltas"]} for r in sc["comparison"]],
            "explanations": sc["explanations"], "population_note": sc["population_note"]}


reset = post("/api/counterfactual/scenario", {"case_id": cid, "operations": []})
rem = post("/api/counterfactual/scenario", {"case_id": cid, "operations": [{"op": "remove", "phenotype": "HP:0001250"}]})
add = post("/api/counterfactual/scenario", {"case_id": cid, "operations": [{"op": "add", "phenotype": "HP:0001251"}]})
bad = post("/api/counterfactual/scenario", {"case_id": cid, "operations": [{"op": "add", "phenotype": "HP:9999999"}]})
out["workflow_b"] = {
    "diagnose_ranking": [(c["rank"], c["disease_id"], c["final_score"]) for c in diag["fused_candidates"]],
    "baseline_reproduces_diagnose": [c["disease_id"] for c in reset["baseline_ranking"]] == [c["disease_id"] for c in diag["fused_candidates"]],
    "reset_all_unchanged": all(r["rank_displacement"] == 0 for r in reset["comparison"] if r["presence"] == "both"),
    "remove_HP0001250": summarize(rem), "add_HP0001251": summarize(add),
    "invalid_add_HP9999999": {"status": bad["status"], "operation": bad["operations"][0], "applied": bad["operations_applied"]},
}
json.dump(out, open("reports/phase5r_e2e.json", "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps(out["workflow_a"]["checks"], indent=1))
print(json.dumps(out["workflow_a"]["semantics_probe"], indent=1))
for k in ("remove_HP0001250", "add_HP0001251"):
    s = out["workflow_b"][k]
    print(k, "\n  baseline:", s["baseline_ranking"], "\n  scenario:", s["counterfactual_ranking"])
    print("  moved:", [(c["disease_id"], c["base_rank"], c["cf_rank"], c["displacement"], c["magnitude"]) for c in s["comparison"] if c["displacement"] != 0])
print("baseline_reproduces_diagnose:", out["workflow_b"]["baseline_reproduces_diagnose"], "| invalid add:", out["workflow_b"]["invalid_add_HP9999999"]["operation"]["status"])
