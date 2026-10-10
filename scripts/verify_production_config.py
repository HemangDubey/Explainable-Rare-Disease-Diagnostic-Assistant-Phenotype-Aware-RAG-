"""Phase 9: verifies the PRODUCTION configuration end to end over real HTTP, on a disposable PostgreSQL (embedded `pgserver`).

Starts the API as a subprocess with APP_ENV=production, DATABASE_URL (PostgreSQL, migrations applied at start), an exact
CORS_ALLOW_ORIGINS, then checks: refusal to start without config, /docs hidden, CORS allow/deny, security headers, registration,
login, authenticated diagnosis, owner isolation, logout revoking the session, persistence across a restart, and that the process
terminates by itself after a graceful stop request. Synthetic data only. Exit code 0 only if every check passes.
    python scripts/verify_production_config.py [--json out.json]
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath("."))
try:
    import pgserver
except ImportError:
    print("pgserver is not installed; skipped")
    sys.exit(3)

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = "https://demo.example.org"
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""), flush=True)


def call(path, body=None, token=None, method=None, headers=None, timeout=300):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h,
                                 method=method or ("POST" if body is not None else "GET"))
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, (json.loads(r.read() or b"{}") if "json" in r.headers.get("content-type", "") else {}), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, (json.loads(e.read() or b"{}") if "json" in e.headers.get("content-type", "") else {}), dict(e.headers)


def start(env):
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    logf = open(os.path.join(tempfile.gettempdir(), "prod_check_api.log"), "w+", encoding="utf-8")     # a file, never an unread pipe
    p = subprocess.Popen([sys.executable, "-W", "ignore", "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
                         env={**os.environ, **env}, stdout=logf, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    p.logfile = logf
    return p


def wait_ready(proc, secs=240):
    end = time.time() + secs
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            if call("/", timeout=3)[1].get("retrieval", {}).get("model"):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return False


def stop(proc):
    t = time.time()
    proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
    try:
        proc.wait(timeout=60)
        return True, time.time() - t
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, time.time() - t


def main():
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    srv = pgserver.get_server(tempfile.mkdtemp(prefix="pg_prod_"))
    try:
        db = srv.get_uri().replace("postgresql://", "postgresql+pg8000://", 1)
        # 1. production without required configuration must refuse to start
        p = start({"APP_ENV": "production", "DATABASE_URL": "", "CORS_ALLOW_ORIGINS": ""})
        try:
            rc = p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill(); rc = None
        p.logfile.seek(0)
        log = p.logfile.read()
        check("production refuses to start without DATABASE_URL / CORS", rc not in (0, None) or "Invalid production configuration" in log,
              "Invalid production configuration" if "Invalid production configuration" in log else f"exit {rc}")

        env = {"APP_ENV": "production", "DATABASE_URL": db, "CORS_ALLOW_ORIGINS": ORIGIN, "AUTO_MIGRATE": "1"}
        p = start(env)
        check("production API starts (PostgreSQL, migrations)", wait_ready(p))
        s, root, hdr = call("/")
        check("health: pipeline + database ready", s == 200 and root.get("status") == "healthy" and (root.get("database") or {}).get("status") == "ok", str(root.get("database")))
        check("/docs and /openapi.json hidden", call("/docs")[0] == 404 and call("/openapi.json")[0] == 404)
        check("security headers present", hdr.get("x-content-type-options") == "nosniff" and "strict-transport-security" in {k.lower() for k in hdr})
        _, _, h1 = call("/api/cases", headers={"Origin": ORIGIN})
        _, _, h2 = call("/api/cases", headers={"Origin": "https://evil.example.com"})
        lk = lambda h, k: next((v for kk, v in h.items() if kk.lower() == k), None)  # noqa: E731
        check("CORS: exact frontend origin allowed", lk(h1, "access-control-allow-origin") == ORIGIN)
        check("CORS: other origin not allowed", lk(h2, "access-control-allow-origin") is None)
        check("CORS: no wildcard / credentials", lk(h1, "access-control-allow-credentials") is None)

        pw = "Synthetic-Prod-Check-Pw1"
        check("registration", call("/api/auth/register", {"email": "prod-a@example.test", "password": pw})[0] == 201)
        s, lg, _ = call("/api/auth/login", {"email": "prod-a@example.test", "password": pw})
        tok = lg.get("access_token")
        check("login returns an opaque session token", s == 200 and bool(tok) and "." not in tok[:4])
        call("/api/auth/register", {"email": "prod-b@example.test", "password": pw})
        tok_b = call("/api/auth/login", {"email": "prod-b@example.test", "password": pw})[1]["access_token"]
        check("protected route without session -> 401", call("/api/cases")[0] == 401)
        check("invalid / expired-looking token -> 401", call("/api/cases", token="not-a-session")[0] == 401)
        s, d, _ = call("/api/diagnose", {"clinical_text": "Synthetic case. Hypotonia, short stature and recurrent seizures.", "top_k": 5}, tok)
        cid = d.get("case_id")
        check("diagnosis on production config", s == 200 and bool(cid) and bool(d.get("fused_candidates")))
        check("saved case listed for its owner", cid in [c["case_id"] for c in call("/api/twin/cases", token=tok)[1].get("cases", [])])
        check("owner isolation: other user gets 404 on the case", call(f"/api/twin/{cid}", token=tok_b)[0] == 404)
        check("owner isolation: other user cannot delete it", call(f"/api/case/{cid}", token=tok_b, method="DELETE")[0] == 404)
        s, _, _ = call("/api/auth/logout", {}, tok)
        check("logout revokes the session", s in (200, 204) and call("/api/cases", token=tok)[0] == 401)

        ok_stop, secs = stop(p)
        check("graceful stop: process exits by itself", ok_stop, f"{secs:.1f}s")

        p = start(env)
        check("restart on the same database", wait_ready(p))
        tok2 = call("/api/auth/login", {"email": "prod-a@example.test", "password": pw})[1].get("access_token")
        check("data persists across restart", cid in [c["case_id"] for c in call("/api/twin/cases", token=tok2)[1].get("cases", [])])
        ok_stop, secs = stop(p)
        check("graceful stop after restart", ok_stop, f"{secs:.1f}s")
    finally:
        srv.cleanup()
    ok = all(c["ok"] for c in checks)
    if out:
        json.dump({"ok": ok, "checks": checks}, open(out, "w", encoding="utf-8"), indent=1)
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
