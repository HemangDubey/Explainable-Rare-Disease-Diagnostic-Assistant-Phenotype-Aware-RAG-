# Platform-neutral API image (Phase 7R; built and smoke-tested in Phase 8R, see reports/PHASE_8R_FINAL_RELEASE_READINESS_REPORT.md).
#
# * No secrets are baked in: GROQ_API_KEY, DATABASE_URL, CORS_ALLOW_ORIGINS ... come from the environment at run time.
# * The ~5 GB of model/index artifacts are NOT in the image: mount them at /app/models and /app/data (see docs/DEPLOYMENT.md).
# * No local model server is used or required. Groq (a remote API) is the only LLM provider.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 APP_ENV=production PORT=8000
WORKDIR /app

COPY requirements-runtime.txt .
# The API runs inference on CPU: install the CPU-only PyTorch build first (~200 MB instead of ~4 GB of CUDA wheels), then the rest.
RUN pip install --retries 10 --timeout 120 --index-url https://download.pytorch.org/whl/cpu torch  && pip install --retries 10 --timeout 120 -r requirements-runtime.txt

COPY src ./src
COPY configs ./configs
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh

RUN useradd --create-home --uid 10001 appuser && chmod +x /entrypoint.sh && mkdir -p /app/data /app/models && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/',timeout=8)" || exit 1
ENTRYPOINT ["/entrypoint.sh"]
