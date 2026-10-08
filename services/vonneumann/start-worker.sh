#!/bin/sh
set -eu
case "${PORT:-8080}" in *[!0-9]*|'') echo 'invalid_worker_port' >&2; exit 1;; esac
test "${PORT:-8080}" -ge 1024 && test "${PORT:-8080}" -le 65535
exec python -m uvicorn vonneumann.server.paper_app:app --host 0.0.0.0 \
  --port "${PORT:-8080}" --workers 1 --lifespan on --no-access-log \
  --timeout-graceful-shutdown 20 --limit-concurrency 32 --limit-max-requests 100000
