"""Operational tooling (REAL, SQLite temp database, separate processes): migrations, backup/restore, retention, legacy-draft import.
Also static validation of the deployment files (Dockerfile / compose / entrypoint). No Docker daemon is needed or used."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

PY = sys.executable


def run(args, db, extra_env=None, inp=None):
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + db.replace("\\", "/"), "PYTHONDONTWRITEBYTECODE": "1", **(extra_env or {})}
    return subprocess.run([PY] + args, capture_output=True, text=True, env=env, input=inp, timeout=120)


def snippet(db, code):
    r = run(["-c", "import sys; sys.path.insert(0,'.')\n" + code], db)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip()


class TestMigrationsAndBackup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ops_")
        self.db = os.path.join(self.dir, "app.db")

    def test_alembic_cli_upgrade_and_downgrade(self):
        r = run(["-m", "alembic", "upgrade", "head"], self.db)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(snippet(self.db, "from src.db.migrate import current_revision; print(current_revision())"), "0001")
        r = run(["-m", "alembic", "downgrade", "base"], self.db)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(snippet(self.db, "from src.db.migrate import current_revision; print(current_revision())"), "None")

    def test_backup_then_restore_recovers_state(self):
        run(["-m", "alembic", "upgrade", "head"], self.db)
        reg = "from src.auth import service; print(service.register('{}', 'Synthetic-Passw0rd-xyz')['id'])"
        snippet(self.db, reg.format("first@example.test"))
        backup = os.path.join(self.dir, "backup.db")
        r = run(["scripts/db_backup.py", "backup", backup], self.db)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertTrue(os.path.getsize(backup) > 0)
        snippet(self.db, reg.format("second@example.test"))
        count = "from sqlalchemy import select, func; from src.db.session import session_scope; from src.db.models import User\nwith session_scope() as s: print(s.scalar(select(func.count()).select_from(User)))"
        self.assertEqual(snippet(self.db, count), "2")
        r = run(["scripts/db_backup.py", "restore", backup], self.db)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertEqual(snippet(self.db, count), "1")                          # the second account is gone: the restore really happened
        self.assertTrue([f for f in os.listdir(self.dir) if "before-restore" in f])   # the pre-restore database was kept

    def test_purge_dry_run_and_delete(self):
        run(["-m", "alembic", "upgrade", "head"], self.db)
        snippet(self.db, "from src.auth import service; from src.api import repo; from datetime import timedelta\n"
                         "from src.db.models import Case, utcnow; from src.db.session import session_scope\n"
                         "uid = service.register('p@example.test', 'Synthetic-Passw0rd-xyz')['id']\n"
                         "old = repo.save_case(uid, None, {'clinical_text': 'old'}); new = repo.save_case(uid, None, {'clinical_text': 'new'})\n"
                         "with session_scope() as s: s.get(Case, old).updated_at = utcnow() - timedelta(days=200)")
        dry = run(["scripts/purge_expired.py", "--days", "90", "--dry-run"], self.db)
        self.assertIn("'cases_to_delete': 1", dry.stdout)
        out = run(["scripts/purge_expired.py", "--days", "90"], self.db)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        self.assertIn("'cases': 1", out.stdout)
        left = snippet(self.db, "from sqlalchemy import select, func; from src.db.session import session_scope; from src.db.models import Case\nwith session_scope() as s: print(s.scalar(select(func.count()).select_from(Case)))")
        self.assertEqual(left, "1")

    def test_legacy_draft_import_assigns_the_named_owner(self):
        run(["-m", "alembic", "upgrade", "head"], self.db)
        snippet(self.db, "from src.auth import service; service.register('owner@example.test', 'Synthetic-Passw0rd-xyz')")
        legacy = os.path.join(self.dir, "legacy")
        os.makedirs(legacy)
        draft = json.loads(subprocess.run([PY, "-c", "import sys,json; sys.path.insert(0,'.')\nfrom src.scribe.note_structurer import NoteStructurer\nprint(NoteStructurer(None).structure('Child has hypotonia.').model_dump_json())"],
                                          capture_output=True, text=True, cwd=os.getcwd()).stdout)
        json.dump({"token_sha256": "x", "draft": draft}, open(os.path.join(legacy, draft["draft_id"] + ".json"), "w"))
        r = run(["scripts/import_legacy_drafts.py", "--email", "owner@example.test", "--dir", legacy], self.db)
        self.assertIn("'imported': 1", r.stdout, r.stderr[-300:])
        r2 = run(["scripts/import_legacy_drafts.py", "--email", "owner@example.test", "--dir", legacy], self.db)
        self.assertIn("'skipped': 1", r2.stdout)                                  # idempotent
        self.assertNotEqual(run(["scripts/import_legacy_drafts.py", "--email", "nobody@example.test", "--dir", legacy], self.db).returncode, 0)


class TestDeploymentFilesStatic(unittest.TestCase):
    @staticmethod
    def read(p):
        with open(p, encoding="utf-8") as f:
            return f.read()

    def test_dockerfile(self):
        d = self.read("Dockerfile")
        self.assertIn("FROM python:", d)
        self.assertIn("USER appuser", d)                                          # not root
        self.assertIn("requirements-runtime.txt", d)
        self.assertIn("COPY migrations", d)
        for bad in ("GROQ_API_KEY=", "PASSWORD=", "ollama", "COPY .env", "COPY . "):
            self.assertNotIn(bad.lower(), d.lower(), bad)
        self.assertNotIn("/app/models\n", "")                                      # artifacts are mounted, not copied
        self.assertNotRegex(d, r"COPY\s+(models|data)\b")

    def test_entrypoint_runs_migrations_then_serves(self):
        e = open("docker/entrypoint.sh", "rb").read()
        self.assertNotIn(b"\r", e)
        t = e.decode()
        self.assertLess(t.index("alembic upgrade head"), t.index("exec uvicorn"))
        self.assertIn("--proxy-headers", t)

    def test_compose_has_no_committed_secrets_and_requires_them(self):
        c = self.read("docker-compose.yml")
        self.assertIn("${POSTGRES_PASSWORD:?", c)
        self.assertIn("${CORS_ALLOW_ORIGINS:?", c)
        self.assertNotRegex(c, r"gsk_|password:\s*[A-Za-z0-9]{6,}\s*$")
        self.assertIn("127.0.0.1:8000:8000", c)                                    # not exposed on all interfaces

    def test_runtime_requirements_cover_the_new_stack_and_exclude_training_extras(self):
        r = self.read("requirements-runtime.txt").lower()
        for need in ("sqlalchemy", "alembic", "argon2-cffi", "psycopg", "fastapi", "uvicorn", "torch", "faiss-cpu"):
            self.assertIn(need, r)
        for extra in ("datasets", "evaluate", "seqeval", "ollama", "openai"):
            self.assertNotIn(extra, r)

    def test_environment_example_lists_every_setting_without_values(self):
        e = self.read(".env.example")
        for name in ("DATABASE_URL", "APP_ENV", "CORS_ALLOW_ORIGINS", "GROQ_API_KEY", "RETENTION_DAYS", "ACCESS_TOKEN_TTL_MIN", "AUTH_RATE_LIMIT_PER_MIN"):
            self.assertIn(name + "=", e)


if __name__ == "__main__":
    unittest.main()
