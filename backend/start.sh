#!/usr/bin/env bash
set -euo pipefail

# Run from any working directory; the FastAPI package lives in backend/app.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-10000}"

# Do not trust arbitrary forwarded IP headers at the ASGI server. Render client
# IPs for rate limiting are handled separately via the configured CF-Connecting-IP.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips 127.0.0.1
