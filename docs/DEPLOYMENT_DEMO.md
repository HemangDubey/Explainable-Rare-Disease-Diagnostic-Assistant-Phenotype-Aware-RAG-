# Demo deployment at ₹0/month (Phase 9)

All numbers below were measured on the development machine unless marked *(platform docs)* or *(unverified)*.

## 1. Can the full pipeline run on free hosting?

| Requirement (measured) | Value |
|---|---|
| Runtime NER weights (`model.safetensors` + tokenizer) | **416 MB** (the other 4.9 GB of `models/` is training checkpoints, not needed) |
| Whole runtime bundle (`scripts/artifacts_bundle.py pack`) | **766 MB** (NER 417 MB + embeddings/FAISS/HPO/ClinVar/gnomAD cache 319 MB) |
| S-PubMedBERT encoder | downloaded from the Hugging Face Hub at first start (about 440 MB, public, no token) |
| RAM after start-up | **941 MB** |
| **Peak RAM** (start + first diagnosis) | **1.73 GB** |
| Cold start (models cached on disk) | 14–28 s; first diagnosis 5 s, later 0.5 s |

| Platform | Limit | Verdict |
|---|---|---|
| Render free web service | RAM figure not stated on the official page (third-party sources say 512 MB); 15 min idle spin-down, ephemeral disk, 750 h/month *(Render docs)* | **Does not fit**: peak 1.73 GB; every wake-up would reload the models |
| Hugging Face Docker Space | CPU Basic is 2 vCPU / 16 GB, **but Docker and Gradio Spaces require a paid plan to create** *(HF docs)* | Not ₹0 |
| Hugging Face Hub (artifacts only) | free public storage, best effort *(HF docs)*; bandwidth caps not documented | Fine for hosting the 766 MB bundle |
| Neon free Postgres | 0.5 GB storage, 100 CU-hours/month, scale-to-zero after 5 min *(Neon docs)* | Fine for a demo database |
| Vercel Hobby | static SPA hosting | Fine for the frontend (non-commercial use) |

**Conclusion:** the complete pipeline (trained BiomedBERT + S-PubMedBERT + FAISS) cannot run on a free cloud web service. It was not
shrunk, quantised, replaced or faked. Smallest honest options:

* **Plan A (recommended, ₹0, most reliable for judging):** run the backend + database on the presenter's laptop with
  `docker compose up` (or `uvicorn`), and open `http://localhost:5173` / the built frontend. No network dependency except Groq.
* **Plan B (₹0, public URL):** Vercel frontend + Neon database + backend on the laptop exposed through a free tunnel (see section 5). The
  laptop must stay on; tunnel URLs may change per run.
* **Plan C (small cost, needs your approval):** any VM/PaaS with at least 2 GB RAM (e.g. a 2 GB instance). Same image, same steps as section 4.

## 2. Environment variables (names only)

Backend: `APP_ENV`, `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, `GROQ_API_KEY`, `GROQ_MODEL` (optional), `NCBI_API_KEY`/`NCBI_EMAIL` (optional),
`AUTO_MIGRATE`, `ALLOW_REGISTRATION`, `ACCESS_TOKEN_TTL_MIN`, `SESSION_ABSOLUTE_HOURS`, `RETENTION_DAYS`, `RATE_LIMIT_PER_MIN`,
`RATE_LIMIT_LLM_PER_MIN`, `AUTH_RATE_LIMIT_PER_MIN`, `MAX_BODY_BYTES`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE_SECONDS`,
`INDIGEN_DEMO_ALLOWED`, `DISABLE_SAFETENSORS_CONVERSION` (already set in code and image), `HF_TOKEN` (only for uploading/private artifact repos),
`POSTGRES_PASSWORD` (docker compose). Frontend (build time, public): `VITE_API_BASE_URL`. **Never put secrets in `VITE_*` variables.**

## 3. Neon database

1. Create a free project at neon.com; copy the **direct** (non-pooler) connection string.
2. Use it as `DATABASE_URL`, rewritten for SQLAlchemy: `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`.
   (With the `-pooler` host the app disables prepared statements automatically; the direct host is simpler.)
3. Migrations run at start when `AUTO_MIGRATE=1`, or manually: `alembic upgrade head`.
4. Neon suspends after 5 idle minutes; the first query after that is slower. `pool_pre_ping` and `pool_recycle` (280 s) handle dropped connections.

## 4. Artifacts and backend (Docker)

```bash
python scripts/artifacts_bundle.py pack --out build/artifacts          # 766 MB runtime bundle
export HF_TOKEN=<token-with-write>                                      # in your shell only
python scripts/artifacts_bundle.py upload --src build/artifacts --repo <hf-user>/<bundle-repo>   # add --private if wanted
# on the machine that runs the backend:
python scripts/artifacts_bundle.py fetch --repo <hf-user>/<bundle-repo> --root .
python scripts/artifacts_bundle.py verify                               # fails clearly if anything required is missing

docker build -t rare-disease-api .
export POSTGRES_PASSWORD=<secret> CORS_ALLOW_ORIGINS=https://<your-frontend-origin> GROQ_API_KEY=<key>
docker compose up -d                                                    # API + PostgreSQL; migrations run at start
curl http://127.0.0.1:8000/                                             # status healthy, database ok
```

Without the artifacts the API starts `degraded` and refuses to run the clinical pipeline; it never substitutes fake output.

## 5. Frontend on Vercel (+ optional tunnel for the laptop backend)

1. Import the repository in Vercel; set **Root Directory = `frontend`** (Framework: Vite; `frontend/vercel.json` provides SPA rewrites and serves the landing page at `/`).
2. Environment variable `VITE_API_BASE_URL` = the public HTTPS URL of the backend.
3. Backend `CORS_ALLOW_ORIGINS` must be exactly the Vercel origin (e.g. `https://<project>.vercel.app`), with no wildcard.
4. Plan B tunnel: `cloudflared tunnel --url http://localhost:8000` prints an `https://….trycloudflare.com` URL *(unverified here: cloudflared was not installed)*.
   A quick-tunnel URL changes on every start, so set `VITE_API_BASE_URL` to it and redeploy the frontend each time.

## 6. Demo rehearsal checklist

Register → run a diagnosis (sample case 1) → verify a phenotype in the Digital Twin → genomic evidence tab → counterfactual → Copilot question →
generate and export a report → Saved Cases → logout → refresh a deep link such as `/digital-twin?case=<id>`.
Groq's free tier allows about 65–70 Copilot answers per day; rehearse sparingly and keep the fallback behaviour in mind (it is labelled).

## 7. Removing a leaked key from Git history (separate, manual, destructive)

1. **Rotate first**: create a new key in the Groq console, update your `.env`/secrets, delete the old key. History rewriting does not make the old key safe.
2. Work on a fresh mirror clone: `git clone --mirror <url> repo.git && cd repo.git`.
3. List the replacement: put the old key in `replacements.txt` as `<OLD_KEY>==>REMOVED` (do not commit this file).
4. `git filter-repo --replace-text replacements.txt` (install `git-filter-repo` first).
5. Review, then `git push --force --mirror` (all collaborators must re-clone). Forks and caches may keep the old content, which is why rotation is step 1.
