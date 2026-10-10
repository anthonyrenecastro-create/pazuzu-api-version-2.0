#!/usr/bin/env bash
# PAZUZU-API v2.0 dev convenience: build and bring the whole stack up.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example (mock providers enabled)."
  cp .env.example .env
fi

exec docker compose up --build
