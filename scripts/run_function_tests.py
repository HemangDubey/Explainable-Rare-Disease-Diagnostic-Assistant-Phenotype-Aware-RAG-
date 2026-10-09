"""Runs the repository's plain-function (pytest-style) tests without pytest and reports PASS / FAIL / SKIP with reasons.
Live ones are labelled: test_api_quality_gate needs a running backend on :8000; test_groq_quality_gate needs GROQ_API_KEY + network.
Usage: python scripts/run_function_tests.py"""
import importlib
import inspect
import os
import pathlib
import socket
import sys
import tempfile

sys.path.insert(0, ".")
MODULES = {"tests.test_phase6_report": "offline", "tests.test_phase6_literature": "offline", "tests.test_input_guard": "uses Groq if configured",
           "tests.test_api_quality_gate": "live backend :8000 (+Groq)", "tests.test_groq_quality_gate": "live Groq"}


def backend_up():
    try:
        socket.create_connection(("127.0.0.1", 8000), timeout=1).close()
        return True
    except OSError:
        return False


results = []
for mod_name, kind in MODULES.items():
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        results.append((mod_name, "FAIL", f"import error {type(e).__name__}"))
        continue
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if not name.startswith("test_") or fn.__module__ != mod.__name__:
            continue
        label = f"{mod_name}::{name} [{kind}]"
        if mod_name.endswith("api_quality_gate") and not backend_up():
            results.append((label, "SKIP", "backend not running on :8000")); continue
        if "live Groq" in kind and not os.environ.get("GROQ_API_KEY"):
            results.append((label, "SKIP", "GROQ_API_KEY not set")); continue
        try:
            fn(pathlib.Path(tempfile.mkdtemp())) if "tmp_path" in inspect.signature(fn).parameters else fn()
            results.append((label, "PASS", ""))
        except Exception as e:
            results.append((label, "FAIL", f"{type(e).__name__}: {str(e)[:200]}"))
for r in results:
    print(" | ".join(r))
c = lambda s: sum(1 for r in results if r[1] == s)
print(f"TOTAL {len(results)}  PASS {c('PASS')}  FAIL {c('FAIL')}  SKIP {c('SKIP')}")
sys.exit(1 if c("FAIL") else 0)
