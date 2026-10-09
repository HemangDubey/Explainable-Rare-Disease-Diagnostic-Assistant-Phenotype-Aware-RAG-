"""Phase 6R concurrency probe with UNCACHED requests (unique note text per case). Writes reports/phase6r_concurrency.json."""
import json, sys, threading, time, urllib.error, urllib.request
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
def call(method, path, body=None, headers=None):
    t = time.time()
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read()), round(time.time() - t, 3)
    except urllib.error.HTTPError as e:
        return e.code, {}, round(time.time() - t, 3)
def case(tag):
    s, d, _ = call("POST", "/api/diagnose", {"clinical_text": f"Patient presents with hypotonia, short stature, developmental delay and recurrent seizures. Reference {tag}.", "top_k": 5})
    return d["case_id"], {"X-Case-Token": d["case_token"]}
out = {}
# 1) slow LLM call in flight + 6 parallel /api/rank
cid, tok = case(int(time.time()))
holder = {}
def slow():
    holder["r"] = call("POST", "/api/reason", {"case_id": cid, "top_k": 5}, tok)
th = threading.Thread(target=slow); th.start(); time.sleep(0.05)
res = []
def rk(): res.append(call("POST", "/api/rank", {"clinical_text": "Patient presents with hypotonia and seizures.", "top_k": 5}))
ts = [threading.Thread(target=rk) for _ in range(6)]
t0 = time.time(); [t.start() for t in ts]; [t.join() for t in ts]; wall = round(time.time() - t0, 2); th.join()
prov = holder["r"][1].get("reasoning", {}).get("provider", {})
out["rank_parallel_during_real_llm_call"] = {"rank_requests": 6, "all_200": all(r[0] == 200 for r in res), "rank_wall_s": wall, "rank_each_s": sorted(r[2] for r in res),
                                              "llm_wall_s": holder["r"][2], "llm_status": prov.get("status"), "llm_cached": prov.get("cached", False)}
time.sleep(65)
# 2) 4 parallel copilot calls on one case (provider tokens-per-minute behaviour)
cid, tok = case(int(time.time()))
qs = ["Why was the top candidate prioritized first?", "Which patient phenotypes match the leading candidate?", "What is the second candidate's final score?", "What gene associations are recorded for the top candidates?"]
cres = []
def cp(q):
    s, r, dt = call("POST", "/api/copilot", {"case_id": cid, "query": q}, tok)
    cres.append({"http": s, "wall_s": dt, "generated_by": r.get("generated_by"), "status": r.get("provider", {}).get("status"), "category": r.get("failure_category"), "attempts": r.get("provider", {}).get("attempts")})
ts = [threading.Thread(target=cp, args=(q,)) for q in qs]
t0 = time.time(); [t.start() for t in ts]; [t.join() for t in ts]
out["copilot_parallel_4"] = {"total_wall_s": round(time.time() - t0, 2), "results": cres}
json.dump(out, open("reports/phase6r_concurrency.json", "w", encoding="utf-8"), indent=1)
print(json.dumps(out, indent=1))
