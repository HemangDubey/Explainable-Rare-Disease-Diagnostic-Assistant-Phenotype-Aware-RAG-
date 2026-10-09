"""Live Doctor Copilot probe: runs the UI's suggested questions through the running API. Prints category + short answer only (no secrets)."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
QS = ["Why was this disease candidate prioritized first?", "Which patient phenotypes match the leading candidate?",
      "What evidence is contributed by Indian population priors?", "What important distinguishing phenotype is missing?",
      "What genetic and confirmatory molecular tests are indicated?"]


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


cid = post("/api/diagnose", {"clinical_text": TEXT, "top_k": 5})["case_id"]
out = []
for q in (sys.argv[1:] or QS):
    t = time.time()
    r = post("/api/copilot", {"query": q, "case_id": cid})
    row = {"q": q, "sec": round(time.time() - t, 1), "generated_by": r.get("generated_by"), "status": r["provider"].get("status"), "reason": r["provider"].get("reason"),
           "cannot_answer": r.get("cannot_answer_from_evidence"), "n_points": len(r.get("evidence_points", [])), "request_id": r.get("request_id"),
           "failure_category": r.get("failure_category"), "answer": r.get("answer", "")[:260]}
    out.append(row)
    print(json.dumps(row, ensure_ascii=True))
    time.sleep(15)
json.dump(out, open("reports/copilot_probe.json", "w", encoding="utf-8"), indent=1)
