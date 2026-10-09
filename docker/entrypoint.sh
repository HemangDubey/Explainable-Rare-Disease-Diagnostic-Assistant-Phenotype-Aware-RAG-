#!/bin/sh
# Applies database migrations (unless RUN_MIGRATIONS=0), then starts the API. Production refuses to start with an invalid configuration.
set -eu
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying database migrations..."
  alembic upgrade head
fi
exec uvicorn src.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
