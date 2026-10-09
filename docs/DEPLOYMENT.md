# Deployment guide (platform-neutral)

Status: research prototype. Read `reports/PHASE_7R_SECURE_DEPLOYMENT_COMPLETION_REPORT.md` for the verified state and the GO/NO-GO decision. Nothing here selects or configures a paid hosting service.

## 1. What runs where
- **API** (FastAPI, `src.api.main:app`): authentication, case/draft/scenario/report storage, the retrieval/ranking pipeline and the Groq calls. Needs ~5 GB of model/index artifacts (§2) and a database (§3).
- **Frontend** (static files from `frontend/dist`): any static host. Built with `VITE_API_BASE_URL`.
- **Database**: SQLite for local development (`data/app.db`, default), **PostgreSQL for any multi-user deployment**.
- **Groq** (remote API): the only language-model provider. No local model server exists or is needed.

## 2. Provisioning the model and index artifacts (~5 GB, not in git)
The repository does not contain them. They must exist on the API host (or a mounted volume) at these paths:
| Path | Content | How to obtain |
|---|---|---|
| `models/biomedbert_phenotype_ner/` | trained BiomedBERT phenotype NER | train with `src/models/train_biomedbert.py` or copy from your artifact store |
| `data/raw/hpo`, `data/raw/disease`, `data/processed/` | HPO ontology, disease annotations, processed tables | `src/knowledge/build_hpo_knowledge_base.py` and the data scripts in `scripts/` |
| `data/embeddings/`, `data/vector_db/` | S-PubMedBERT / MiniLM embeddings and FAISS indexes | build scripts in `src/retrieval` / `scripts/`, verify with `python scripts/validate_embeddings.py` |
| `data/raw/gnomad/gene_cache` | gnomAD × ClinVar gene-level population evidence | population build scripts (IndiGen data are not available) |
| Hugging Face cache | `pritamdeka/S-PubMedBert-MS-MARCO`, MiniLM | downloaded on first start, or pre-populate `HF_HOME` and set `HF_HUB_OFFLINE=1` |
Copy them with your normal artifact tooling (object storage, rsync, a mounted volume). If they are missing the API is designed to start in a degraded mode (`GET /` shows the retrieval error and database status); this degraded start was not exercised in validation.

## 3. Database, migrations and persistence
Set `DATABASE_URL` (never commit it):
- development default: `sqlite:///data/app.db` (created automatically; WAL mode, foreign keys on)
- PostgreSQL: `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` (or `postgresql+pg8000://…` for the pure-Python driver)

Schema is managed by **Alembic** (`migrations/`). Apply it with `alembic upgrade head` (the container entrypoint does this unless `RUN_MIGRATIONS=0`). `AUTO_MIGRATE=1` makes the API migrate at startup (default in development; default **off** in production, where the API reports `database.status: schema_outdated` instead). Tables: `users`, `auth_sessions`, `cases`, `scenarios`, `reports`, `drafts`; every record carries `owner_id`, scenarios/reports reference their case with `ON DELETE CASCADE`.

Upgrading from Phase 5R/6R: cases, scenarios and reports were in memory and are not recoverable. File drafts (`data/drafts/*.json`) can be imported once: `python scripts/import_legacy_drafts.py --email you@example.org`.

### Backup and restore
- SQLite: `python scripts/db_backup.py backup backups/app-$(date +%F).db`; restore (API stopped): `python scripts/db_backup.py restore backups/app-….db`.
- PostgreSQL: `pg_dump --format=custom --file=backup.dump "<connection string>"`; restore with `pg_restore --clean --if-exists --dbname="<connection string>" backup.dump`. `python scripts/db_backup.py backup x` prints these commands for the configured URL.
- Backups contain clinical text and password hashes: encrypt them and restrict access.

### Retention and deletion
Users can delete a case (with its scenarios and reports) with `DELETE /api/case/{id}` and a draft with `DELETE /api/scribe/draft/{id}`. Automatic retention: set `RETENTION_DAYS=N` (the API purges cases/drafts not updated for N days every 6 hours) or run `python scripts/purge_expired.py --days N [--dry-run]` from a scheduler. There is no default retention (0 = keep). Deleted data may persist in backups until those expire.

## 4. Authentication model
Email + password accounts (`/api/auth/register`, `/login`, `/logout`, `/me`). Passwords are hashed with argon2id. Login returns an opaque 256-bit bearer token; only its SHA-256 is stored server-side, sessions have a sliding idle expiry (`ACCESS_TOKEN_TTL_MIN`, default 60) and an absolute cap (`SESSION_ABSOLUTE_HOURS`, default 12), and logout revokes server-side. There is **no signing secret** to configure or leak. The token travels only in the `Authorization: Bearer` header (no cookies → no CSRF surface). Every `/api/*` route except `/api/auth/register` and `/api/auth/login` requires a valid session; records are filtered by `owner_id`, so another user's ids behave as "not found". Account lock-out and rate limits: §6. Limitations: no email verification or password reset, no MFA, registration can reveal that an email is already taken (set `ALLOW_REGISTRATION=0` for closed deployments).

## 5. Configuration (environment variables only)
See `.env.example` for the full list. Required in production: `APP_ENV=production`, `DATABASE_URL`, `CORS_ALLOW_ORIGINS` (trusted https origins, no localhost, no `*`), `GROQ_API_KEY` for LLM features. In production the API **refuses to start** if `DATABASE_URL` or a non-localhost `CORS_ALLOW_ORIGINS` is missing, and `/docs`, `/redoc`, `/openapi.json` are disabled. `GROQ_MODEL` overrides `llm.model` in `configs/config.yaml`.

## 6. HTTPS, CORS and rate limiting
- **TLS is terminated outside the app** (reverse proxy or platform load balancer). The API only speaks HTTP and trusts `--proxy-headers`; in production it sends `Strict-Transport-Security`. Serve the frontend over HTTPS and set `CORS_ALLOW_ORIGINS` to that exact origin. Bearer tokens must never be sent over plain HTTP.
- CORS is an allowlist with no credentials and only `Content-Type` / `Authorization` headers.
- Rate limits (`RATE_LIMIT_PER_MIN`, `RATE_LIMIT_LLM_PER_MIN`, `AUTH_RATE_LIMIT_PER_MIN`) and the account lock-out counters: the request limits are **process-local, per client IP** (behind a proxy every user may share one IP, and several API replicas each keep their own counters). The lock-out counter (`LOGIN_MAX_FAILURES` failures → `LOGIN_LOCK_MINUTES` minutes) is stored in the database and therefore shared. For multi-instance deployments add rate limiting at the gateway/WAF.

## 7. Running
Local development:
```
python -m venv .venv && .venv\Scripts\activate         # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                    # fill GROQ_API_KEY
python src/api/main.py                                  # http://localhost:8000  (SQLite, auto-migrated)
cd frontend && npm ci && npm run dev                    # http://localhost:5173
```
Production-style (reference `docker-compose.yml`: API + PostgreSQL): `POSTGRES_PASSWORD=… CORS_ALLOW_ORIGINS=https://app.example.org GROQ_API_KEY=… docker compose up --build`, with `./models` and `./data` provisioned (§2). Frontend: `cd frontend && VITE_API_BASE_URL=https://api.example.org npm run build`, then publish `frontend/dist`. **The Docker image and compose file were not built or run in the validation environment** (Docker CLI present, daemon not running); `docker compose config` and static checks passed.

## 8. Health and troubleshooting
`GET /` is public and returns `{status, retrieval, llm:{status,model}, database:{status}}` with no secrets (`database.status`: `ok`, `schema_outdated`, `unavailable`). If the database is down, protected routes answer `503 database_unavailable` and recover when it returns. Logs contain paths, statuses, ids and categories — never note text, prompts, passwords or tokens.

## 9. Privacy
LLM features (`/api/reason`, `/api/explain`, `/api/copilot`, `/api/input/enhance`, `explain=true`) send the relevant clinical text and evidence to Groq, an external provider. Assess this against your obligations before using real patient data; no HIPAA/GDPR/DPDP compliance is claimed. The database stores clinical text, generated evidence and drafts under the owner's account; protect it with disk encryption, access control and backups policy. Use synthetic data for testing.
