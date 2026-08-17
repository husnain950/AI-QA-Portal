#!/usr/bin/env bash
# Deploy the CRX API to CodeRun with persistent storage.
#
# Persistent volume at /app/data keeps SQLite DB + blob uploads alive across
# container restarts and image rebuilds. The baked seed corpus at /seed/corpus/
# auto-populates the DB on first boot (empty volume).
#
# Prerequisites:
#   - coderun CLI installed and authenticated (`coderun login`)
#   - Docker image built locally or via `--build` flag
#
# Usage:
#   bash tools/deploy_coderun.sh                 # fresh deploy
#   bash tools/deploy_coderun.sh --redeploy ID   # update existing deployment
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

APP_NAME="${CRX_APP_NAME:-crx-api}"
STORAGE_SIZE="${CRX_STORAGE_SIZE:-5Gi}"
STORAGE_PATH="/app/data"
HTTP_PORT=8000
ENV_FILE="${ROOT}/.env"

# Load .env for OPENPATHS keys etc. if present. Strip host-relative corpus/db
# paths so they cannot override the image defaults (/data/corpus/..., /app/data).
ENV_FLAG=""
FILTERED_ENV=""
if [[ -f "$ENV_FILE" ]]; then
  FILTERED_ENV="$(mktemp)"
  trap 'rm -f "$FILTERED_ENV"' EXIT
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    FILTER_PYTHON="$ROOT/.venv/bin/python"
  else
    FILTER_PYTHON="python3"
  fi
  "$FILTER_PYTHON" "$ROOT/tools/filter_deploy_env.py" "$ENV_FILE" "$FILTERED_ENV"
  ENV_FLAG="--env-file $FILTERED_ENV"
fi

# Build the seed archive (PDFs + JSONs) so the image includes corpus data.
echo "Building seed archive..."
make -C "$ROOT" seed-archive

if [[ "${1:-}" == "--redeploy" && -n "${2:-}" ]]; then
  DEPLOY_ID="$2"
  echo "Redeploying $DEPLOY_ID from source..."
  coderun deploy --build "$ROOT" \
    --name "$APP_NAME" \
    --http-port "$HTTP_PORT" \
    --storage-size "$STORAGE_SIZE" \
    --storage-path "$STORAGE_PATH" \
    $ENV_FLAG
else
  echo "Fresh deploy of $APP_NAME with ${STORAGE_SIZE} persistent volume at ${STORAGE_PATH}..."
  coderun deploy --build "$ROOT" \
    --name "$APP_NAME" \
    --http-port "$HTTP_PORT" \
    --storage-size "$STORAGE_SIZE" \
    --storage-path "$STORAGE_PATH" \
    $ENV_FLAG
fi

echo ""
echo "Deployment complete. The persistent volume at $STORAGE_PATH survives redeploys."
echo "On first boot with an empty volume, the API auto-seeds from /seed/corpus/."
