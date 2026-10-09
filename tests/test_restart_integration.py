"""Phase 7R REAL integration tests that run separate processes (slow: each backend start loads the models).

* SQLite: a real backend process is started, stopped and started again against the same database file.
* PostgreSQL: the same flow against a genuine PostgreSQL server (embedded `pgserver` wheel, pg8000 driver); plus concurrency/cascade checks.
Skipped (not faked) when pgserver is unavailable. Synthetic data only.
"""
import os
import subprocess
import sys
import unittest

PY = sys.executable


def run(cmd, timeout=500):
    p = subprocess.run([PY] + cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return p.returncode, (p.stdout + p.stderr)[-2500:]


class TestRestartSqlite(unittest.TestCase):
    def test_records_survive_a_real_backend_restart(self):
        rc, out = run(["scripts/verify_persistence.py"])
        self.assertEqual(rc, 0, out)
        self.assertIn('"same_ranking_for_same_input": true', out)
        self.assertIn('"user_b_still_isolated": true', out)


class TestPostgres(unittest.TestCase):
    def setUp(self):
        try:
            import pgserver  # noqa: F401
        except ImportError:
            self.skipTest("pgserver (embedded PostgreSQL) is not installed")

    def test_restart_flow_on_postgresql(self):
        rc, out = run(["scripts/verify_persistence_postgres.py"], timeout=580)
        self.assertEqual(rc, 0, out)
        self.assertIn('"records_created": true', out)

    def test_concurrency_ownership_and_cascade_on_postgresql(self):
        rc, out = run(["scripts/verify_postgres_concurrency.py"], timeout=300)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("false", out)


if __name__ == "__main__":
    unittest.main()
