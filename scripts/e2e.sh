#!/usr/bin/env bash
# Medo e2e golden paths (ticket 32) — single command:
#   bash scripts/e2e.sh          # build+up stack, install chromium, run suite
#   bash scripts/e2e.sh --down   # tear the e2e stack down afterwards
#
# Stack: compose.dev.yaml + compose.e2e.yaml overlay (project medo-e2e).
# App:  https://localhost:3000 · API: https://localhost (Caddy internal CA).
set -euo pipefail
cd "$(dirname "$0")/.."

DOWN_AFTER=0
if [ "${1:-}" = "--down" ]; then DOWN_AFTER=1; shift; fi

# GITHUB_PAT needed for GHCR base images during build. Falls back to the
# docs-repo .env at D:\medo\.env (../../.env relative to medo-infra).
if [ -z "${GITHUB_PAT:-}" ] && [ -f ../../.env ]; then
  set -a; . ../../.env; set +a
fi
: "${GITHUB_PAT:?GITHUB_PAT missing — export it or fill ../../.env}"
export GITHUB_PAT

COMPOSE=(docker compose -f compose.dev.yaml -f compose.e2e.yaml --profile e2e)

echo "== building + starting e2e stack (project medo-e2e)"
"${COMPOSE[@]}" up -d --build

echo "== waiting for API health (https://localhost/health)"
for i in $(seq 1 60); do
  if curl -sfk --max-time 5 https://localhost/health >/dev/null 2>&1; then
    echo "   api healthy after ~$((i*5))s"
    break
  fi
  [ "$i" = "60" ] && { echo "FATAL: api never became healthy"; exit 1; }
  sleep 5
done

echo "== waiting for app (https://localhost:3000)"
for i in $(seq 1 60); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://localhost:3000/ || true)
  if [ "$code" = "200" ]; then
    echo "   app responding (HTTP $code)"
    break
  fi
  [ "$i" = "60" ] && { echo "FATAL: app never responded"; exit 1; }
  sleep 5
done

cd e2e
echo "== npm ci"
npm ci
echo "== playwright install chromium"
npx playwright install chromium

echo "== running golden paths"
set +e
npx playwright test "$@"
STATUS=$?
set -e

if [ "$DOWN_AFTER" = "1" ]; then
  echo "== tearing down e2e stack"
  "${COMPOSE[@]}" down
fi

echo "== done (exit $STATUS). Stack left up; teardown: docker compose -f compose.dev.yaml -f compose.e2e.yaml --profile e2e down"
exit "$STATUS"
