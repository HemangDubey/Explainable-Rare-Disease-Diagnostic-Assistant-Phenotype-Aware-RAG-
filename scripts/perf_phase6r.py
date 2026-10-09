"""Phase 6R reproducible latency / concurrency check against a RUNNING backend (real pipeline, real Groq). Writes reports/phase6r_perf.json.
Only latencies and counts are logged: no clinical text. Usage: python scripts/perf_phase6r.py [base_url]
Groq calls are spaced to respect the account's tokens-per-minute limit, except in the deliberate concurrency probe."""
import json
import platform
import statistics as st
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TEXTS = ["Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.",
         "Child with microcephaly, ataxia and intellectual disability.",
         "Infant with failure to thrive, hepatomegaly and hypoglycemia."]


def call(method, path, body=None, headers=None, timeout=300):
    t = time.time()
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, {}, time.time() - t


def summary(xs):
    xs = sorted(xs)
    return {"n": len(xs), "min_s": round(xs[0], 3), "median_s": round(st.median(xs), 3), "max_s": round(xs[-1], 3)}


out = {"environment": {"platform": platform.platform(), "python": platform.python_version(), "machine": platform.machine(), "note": "single developer laptop, backend + client on the same host"}}
try:
    import os
    out["environment"]["cpu_count"] = os.cpu_count()
except Exception:
    pass

# ---- diagnose (no LLM): cold vs warm, with per-stage numbers reported by the backend itself ----
runs = []
for i, text in enumerate(TEXTS * 2):
    s, d, dt = call("POST", "/api/diagnose", {"clinical_text": text, "top_k": 5})
    lat = (d.get("retrieval_metadata") or {}).get("latency_ms", {})
    runs.append({"i": i, "total_s": round(dt, 3), "ner_and_hpo_ms": lat.get("ner_and_mapping"), "retrieval_ms": lat.get("retrieval"), "status": s})
out["diagnose_sequence"] = {"first_call_after_start_is_cold": True, "runs": runs,
                            "warm_total": summary([r["total_s"] for r in runs[1:]]),
                            "warm_ner_and_hpo_ms": summary([r["ner_and_hpo_ms"] / 1000 for r in runs[1:] if r["ner_and_hpo_ms"]]),
                            "warm_retrieval_ms": summary([r["retrieval_ms"] / 1000 for r in runs[1:] if r["retrieval_ms"]])}
s, d, _ = call("POST", "/api/diagnose", {"clinical_text": TEXTS[0], "top_k": 5})
cid, tok = d["case_id"], {"X-Case-Token": d["case_token"]}

# ---- /api/rank alone (ranking + retrieval) ----
rk = [call("POST", "/api/rank", {"clinical_text": TEXTS[0], "top_k": 5})[2] for _ in range(5)]
out["rank_warm"] = summary(rk)

# ---- Groq reasoning (spaced >60 s apart: ~6k tokens each against an 8k tokens/minute limit) ----
reason = []
for i in range(3):
    s, r, dt = call("POST", "/api/reason", {"case_id": cid, "top_k": 5}, tok)
    prov = r.get("reasoning", {}).get("provider", {})
    reason.append({"i": i, "wall_s": round(dt, 2), "status": prov.get("status"), "fallback": prov.get("fallback"), "attempts": prov.get("attempts"), "http": s})
    if i < 2:
        time.sleep(65)
    # the reasoner caches identical successful requests, so vary by clearing via a different case each time
    s, d, _ = call("POST", "/api/diagnose", {"clinical_text": TEXTS[(i + 1) % 3], "top_k": 5})
    cid, tok = d["case_id"], {"X-Case-Token": d["case_token"]}
out["groq_reasoning"] = {"runs": reason}

# ---- copilot (spaced 20 s) ----
cop = []
for i, q in enumerate(["Why was the top candidate prioritized first?", "Which patient phenotypes match the leading candidate?", "What is the patient's blood pressure?"]):
    s, r, dt = call("POST", "/api/copilot", {"case_id": cid, "query": q}, tok)
    cop.append({"i": i, "wall_s": round(dt, 2), "generated_by": r.get("generated_by"), "status": r.get("provider", {}).get("status"), "http": s})
    time.sleep(20)
out["copilot"] = {"runs": cop}

# ---- concurrency 1: 6 parallel /api/rank while one Groq reasoning call is in flight (does a slow LLM block retrieval?) ----
time.sleep(65)
s, d, _ = call("POST", "/api/diagnose", {"clinical_text": TEXTS[1], "top_k": 5})
cid2, tok2 = d["case_id"], {"X-Case-Token": d["case_token"]}
holder = {}
def slow():
    holder["r"] = call("POST", "/api/reason", {"case_id": cid2, "top_k": 5}, tok2)
th = threading.Thread(target=slow); th.start()
time.sleep(0.2)
res = []
def rank_one():
    res.append(call("POST", "/api/rank", {"clinical_text": TEXTS[0], "top_k": 5}))
ts = [threading.Thread(target=rank_one) for _ in range(6)]
t0 = time.time()
[t.start() for t in ts]; [t.join() for t in ts]
th.join()
out["concurrency_rank_during_llm"] = {"parallel_rank_requests": 6, "all_http_200": all(r[0] == 200 for r in res), "wall_s_for_all_rank": round(time.time() - t0, 2),
                                      "per_request": summary([r[2] for r in res]), "llm_call_wall_s": round(holder["r"][2], 2),
                                      "llm_status": holder["r"][1].get("reasoning", {}).get("provider", {}).get("status")}

# ---- concurrency 2: 4 parallel copilot calls (provider rate-limit behaviour) ----
time.sleep(65)
cres = []
def cop_one(q):
    s, r, dt = call("POST", "/api/copilot", {"case_id": cid2, "query": q}, tok2)
    cres.append({"http": s, "wall_s": round(dt, 2), "generated_by": r.get("generated_by"), "status": r.get("provider", {}).get("status"), "category": r.get("failure_category")})
qs = ["Why was the top candidate prioritized first?", "Which phenotypes match the leading candidate?", "What is the second candidate's score?", "What gene associations are recorded?"]
ts = [threading.Thread(target=cop_one, args=(q,)) for q in qs]
t0 = time.time()
[t.start() for t in ts]; [t.join() for t in ts]
out["concurrency_copilot_parallel_4"] = {"wall_s_total": round(time.time() - t0, 2), "results": cres}
json.dump(out, open("reports/phase6r_perf.json", "w", encoding="utf-8"), indent=1)
print(json.dumps(out, indent=1)[:6000])
