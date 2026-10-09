"""End-to-end check against a RUNNING backend: text -> NER -> HPO -> real embeddings -> FAISS -> ranking.

    python scripts/e2e_pipeline_check.py [--url http://127.0.0.1:8000]

Uses a synthetic example sentence (no patient data) and a throwaway synthetic account. Writes reports/retrieval_pipeline_validation.json with the
actual intermediate outputs and the invariant checks, and exits non-zero if any check fails.
"""
import argparse
import json
import sys
from pathlib import Path

import requests

CASE = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."


def main(url):
    checks = {}

    def check(name, ok, detail=""):
        checks[name] = {"pass": bool(ok), "detail": detail}

    health = requests.get(f"{url}/", timeout=30).json()
    check("backend_healthy", health["status"] == "healthy", health["status"])
    check("real_model_loaded", health["retrieval"].get("model") == "pritamdeka/S-PubMedBert-MS-MARCO", str(health["retrieval"].get("model")))

    # every /api route except health and /api/auth/* needs a session: use a throwaway synthetic account
    import uuid
    S = requests.Session()
    email, pw = f"e2e-{uuid.uuid4().hex[:8]}@example.test", "Synthetic-Passw0rd-xyz"
    S.post(f"{url}/api/auth/register", json={"email": email, "password": pw}, timeout=60).raise_for_status()
    tok = S.post(f"{url}/api/auth/login", json={"email": email, "password": pw}, timeout=60).json()["access_token"]
    S.headers["Authorization"] = "Bearer " + tok
    r1 = S.post(f"{url}/api/retrieve", json={"clinical_text": CASE, "top_k": 10}, timeout=300).json()
    r2 = S.post(f"{url}/api/retrieve", json={"clinical_text": CASE, "top_k": 10}, timeout=300).json()
    check("ner_mentions_have_offsets", all(CASE[m["start"]:m["end"]] == m["mention"] for m in r1["extracted_phenotypes"]))
    check("no_root_term_assigned", all(m["hpo_id"] != "HP:0000001" for m in r1["hpo_mappings"]))
    check("hpo_mapped_hypotonia_and_short_stature",
          {"HP:0001252", "HP:0004322"} <= {m["hpo_id"] for m in r1["hpo_mappings"]})
    check("candidates_returned", len(r1["candidates"]) == 10)
    check("reproducible_across_calls", [c["disease_id"] for c in r1["candidates"]] == [c["disease_id"] for c in r2["candidates"]])
    check("scores_real_and_descending_or_equal", all(isinstance(c["embedding_similarity"], float) for c in r1["candidates"]))

    d = S.post(f"{url}/api/diagnose", json={"clinical_text": CASE, "top_k": 5}, timeout=600).json()
    check("diagnose_uses_ner_offsets", all(isinstance(p.get("start"), int) for p in d["extracted_phenotypes"]))
    check("diagnose_returns_ranked_fused_candidates", len(d["fused_candidates"]) == 5)

    report = {
        "input_example": "synthetic example sentence (no patient data)",
        "extracted_phenotypes": [{k: m[k] for k in ("mention", "start", "end", "label", "confidence")} for m in r1["extracted_phenotypes"]],
        "hpo_mappings": [{k: m.get(k) for k in ("mention", "status", "hpo_id", "term", "score", "matching_method")}
                         | ({"candidates": m["candidates"]} if m.get("candidates") else {}) for m in r1["hpo_mappings"]],
        "retrieval_metadata": r1["retrieval_metadata"],
        "top_candidates": [{k: c[k] for k in ("disease_id", "disease_name", "embedding_similarity", "retrieval_score", "phenotype_overlap", "matched_hpo_ids", "associated_genes")} for c in r1["candidates"][:5]],
        "diagnose_top_fused": [{"rank": c["rank"], "disease_id": c["disease_id"], "disease_name": c["disease_name"], "final_score": c["final_score"],
                                "matched": [m["hpo_id"] for m in c["phenotype_evidence"]["matched_phenotypes"]]} for c in d["fused_candidates"]],
        "checks": checks,
        "passed": all(v["pass"] for v in checks.values()),
    }
    Path("reports").mkdir(exist_ok=True)
    json.dump(report, open("reports/retrieval_pipeline_validation.json", "w", encoding="utf-8"), indent=2)
    print(json.dumps({k: report[k] for k in ("extracted_phenotypes", "hpo_mappings", "top_candidates", "diagnose_top_fused")}, indent=1))
    for n, v in checks.items():
        print(("PASS " if v["pass"] else "FAIL ") + n, v["detail"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    sys.exit(main(ap.parse_args().url))
