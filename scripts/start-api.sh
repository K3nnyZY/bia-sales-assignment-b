#!/bin/sh
set -eu
exec uvicorn app.main:app --host "${BIND_HOST:-0.0.0.0}" --port "${PORT:-8000}" --no-proxy-headers
