"""Real end-to-end Phase 4R run against the running API (diagnose -> reason -> differential -> copilot). No fixtures.
Usage: python scripts/e2e_phase4r.py [base_url]  ->  reports/phase4r_e2e.json"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


def post(path, body, timeout=1200):
    t = time.time()
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return r, round(time.time() - t, 1)


out = {"clinical_text": TEXT, "steps": {}}
d, s = post("/api/diagnose", {"clinical_text": TEXT, "top_k": 5})
out["steps"]["diagnose"] = {"seconds": s, "reasoning_status": d["reasoning"]["provider"]["status"], "n_candidates": len(d["fused_candidates"]),
                            "ranking": [(c["rank"], c["disease_id"], c["final_score"], c["phenotype_evidence"]["label"]) for c in d["fused_candidates"]],
                            "score_breakdown_matches_backend": all(c["score_breakdown"]["matches_backend"] for c in d["fused_candidates"])}
r, s = post("/api/reason", {"case_id": d["case_id"], "top_k": 5})
prov = r["reasoning"]["provider"]
out["steps"]["reason"] = {"seconds": s, "provider": {k: prov[k] for k in ("name", "model", "status", "attempts", "latency_ms", "fallback", "reason")},
                          "grounding": prov.get("grounding"), "candidates": r["reasoning"]["candidates"]}
df, s = post("/api/differential", {"case_id": d["case_id"], "top_k": 5})
out["steps"]["differential"] = {"seconds": s, "n": len(df["differential"]["top_candidates"]) if "differential" in df else None,
                                "keys": list(df.keys())}
c, s = post("/api/copilot", {"query": "Why was the top candidate ranked first, and what is unverified?", "case_id": d["case_id"]})
out["steps"]["copilot"] = {"seconds": s, "provider": c.get("provider"), "fallback": c.get("fallback"), "answer": c.get("answer") or c.get("text"),
                           "keys": list(c.keys())}
json.dump(out, open("reports/phase4r_e2e.json", "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("candidates", "answer")} for k, v in out["steps"].items()}, indent=1, default=str)[:3500])
