"""Runs scripts/verify_persistence.py against a REAL PostgreSQL server (embedded `pgserver` wheel, a genuine PostgreSQL build), using the
pure-Python pg8000 driver. Exit code 0 only if every restart/isolation check passes. Synthetic data only; the temporary server is removed.
Usage: python scripts/verify_persistence_postgres.py [--json out.json]"""
import subprocess
import sys
import tempfile

try:
    import pgserver
except ImportError:
    print("pgserver is not installed (pip install pgserver); PostgreSQL verification skipped")
    sys.exit(3)

out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
srv = pgserver.get_server(tempfile.mkdtemp(prefix="pg_verify_"))
try:
    url = srv.get_uri().replace("postgresql://", "postgresql+pg8000://", 1)
    cmd = [sys.executable, "scripts/verify_persistence.py", "--database-url", url] + (["--json", out] if out else [])
    rc = subprocess.call(cmd)
finally:
    srv.cleanup()
sys.exit(rc)
