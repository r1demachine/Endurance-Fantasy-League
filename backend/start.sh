#!/usr/bin/env bash
set -euo pipefail

# Run from any working directory; the FastAPI package lives in backend/app.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-10000}"
APP_ENV="${APP_ENV:-development}"
# Local default trusts only localhost. Production must explicitly configure the
# actual trusted proxy hops in the hosting environment.
if [[ "$APP_ENV" == "production" && -z "${FORWARDED_ALLOW_IPS:-}" ]]; then
  echo "ERROR: set FORWARDED_ALLOW_IPS for the production reverse proxy (Render: * only while all traffic is forced through Render's proxy)." >&2
  exit 1
fi
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
