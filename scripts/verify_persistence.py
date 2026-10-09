"""Real process-restart verification (synthetic data only).

Starts the backend as a separate process against a database, creates two users and a full set of records for user A (case, scenario,
report, draft), STOPS the process, starts it again against the same database, and checks that everything is recovered, that the
ranking for the same input is identical, and that user B still cannot reach any of user A's records.

Usage:  python scripts/verify_persistence.py [--database-url URL] [--port N] [--json out.json]
Default database: a fresh temporary SQLite file. Exit code 0 only if every check passes.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

TEXT = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures."
PW = "Synthetic-Passw0rd-xyz"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def api(base, method, path, body=None, token=None, timeout=180):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw or b"{}")
            except ValueError:                       # e.g. the HTML report export
                return r.status, {"_non_json_bytes": len(raw)}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


class Backend:
    def __init__(self, env, port, logfile):
        self.port, self.base = port, f"http://127.0.0.1:{port}"
        self.log = open(logfile, "ab")
        self.proc = subprocess.Popen([sys.executable, "-c", f"import uvicorn; uvicorn.run('src.api.main:app', host='127.0.0.1', port={port}, log_level='warning')"],
                                     env=env, stdout=self.log, stderr=subprocess.STDOUT, cwd=os.getcwd())

    def wait_ready(self, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("backend exited early (see log)")
            try:
                st, body = api(self.base, "GET", "/", timeout=5)
                if st == 200 and body.get("database", {}).get("status") == "ok":
                    return round(time.time() - t0, 1)
            except Exception:
                pass
            time.sleep(2)
        raise TimeoutError("backend did not become ready")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="persist_")
    url = a.database_url or "sqlite:///" + os.path.join(tmp, "app.db").replace("\\", "/")
    env = {**os.environ, "DATABASE_URL": url, "AUTO_MIGRATE": "1", "PYTHONDONTWRITEBYTECODE": "1", "CORS_ALLOW_ORIGINS": "http://localhost:5173"}
    port = a.port or free_port()
    checks, ids = {}, {}
    be = Backend(env, port, os.path.join(tmp, "backend.log"))
    try:
        checks["first_start_seconds"] = be.wait_ready()
        base = be.base
        ea, eb = f"a-{os.urandom(3).hex()}@example.test", f"b-{os.urandom(3).hex()}@example.test"
        for e in (ea, eb):
            assert api(base, "POST", "/api/auth/register", {"email": e, "password": PW})[0] == 201
        ta = api(base, "POST", "/api/auth/login", {"email": ea, "password": PW})[1]["access_token"]
        tb = api(base, "POST", "/api/auth/login", {"email": eb, "password": PW})[1]["access_token"]
        d = api(base, "POST", "/api/diagnose", {"clinical_text": TEXT, "top_k": 3}, ta)[1]
        ids["case"] = d["case_id"]
        ids["ranking"] = [(c["disease_id"], c["final_score"]) for c in d["fused_candidates"]]
        ids["scenario"] = api(base, "POST", "/api/counterfactual/scenario", {"case_id": ids["case"], "operations": [{"op": "remove", "phenotype": "HP:0001250"}]}, ta)[1]["scenario_id"]
        ids["report"] = api(base, "POST", "/api/report/generate", {"case_id": ids["case"]}, ta)[1]["header"]["report_id"]
        ids["draft"] = api(base, "POST", "/api/scribe/draft", {"clinical_text": TEXT}, ta)[1]["draft_id"]
        checks["records_created"] = all(ids.values())
    finally:
        be.stop()
    time.sleep(1)
    checks["port_closed_after_stop"] = not _port_open(port)

    be2 = Backend(env, port, os.path.join(tmp, "backend2.log"))      # a brand-new process: nothing survives except the database
    try:
        checks["second_start_seconds"] = be2.wait_ready()
        base = be2.base
        checks["old_session_still_valid"] = api(base, "GET", "/api/auth/me", token=ta)[0] == 200
        checks["case_recovered"] = api(base, "POST", "/api/differential", {"case_id": ids["case"]}, ta)[0] == 200
        checks["scenario_recovered"] = api(base, "GET", f"/api/counterfactual/scenario/{ids['scenario']}", token=ta)[0] == 200
        checks["report_recovered"] = api(base, "GET", f"/api/report/{ids['report']}", token=ta)[0] == 200
        checks["report_export_recovered"] = api(base, "GET", f"/api/report/{ids['report']}/export", token=ta)[0] == 200
        checks["draft_recovered"] = api(base, "GET", f"/api/scribe/draft/{ids['draft']}", token=ta)[0] == 200
        d2 = api(base, "POST", "/api/diagnose", {"clinical_text": TEXT, "top_k": 3}, ta)[1]
        checks["same_ranking_for_same_input"] = [(c["disease_id"], c["final_score"]) for c in d2["fused_candidates"]] == ids["ranking"]
        checks["user_b_still_isolated"] = all(code in (404, 400) for code in (
            api(base, "GET", f"/api/counterfactual/scenario/{ids['scenario']}", token=tb)[0], api(base, "GET", f"/api/report/{ids['report']}", token=tb)[0],
            api(base, "GET", f"/api/scribe/draft/{ids['draft']}", token=tb)[0], api(base, "POST", "/api/reason", {"case_id": ids["case"]}, tb)[0]))
        checks["logout_persists"] = api(base, "POST", "/api/auth/logout", token=ta)[0] == 200 and api(base, "GET", "/api/auth/me", token=ta)[0] == 401
    finally:
        be2.stop()
    out = {"database": url.split("@")[-1] if "@" in url else url.split("///")[0] + "///<temp file>", "checks": checks, "ok": all(v for k, v in checks.items() if not k.endswith("seconds"))}
    print(json.dumps(out, indent=1))
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), indent=1)
    sys.exit(0 if out["ok"] else 1)


def _port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
