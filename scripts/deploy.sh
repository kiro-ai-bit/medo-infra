#!/usr/bin/env bash
# Medo prod deploy — runs ON the EC2 host in /opt/medo (pushed there by release.sh).
# Pulls SHA-tagged GHCR images, health-gates ~60s, auto-rolls back to .last-good.
#
#   bash scripts/deploy.sh            # deploy tags from .env
#   bash scripts/deploy.sh --no-pull  # skip image pull (local rebuilds)
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f compose.yaml --env-file .env)
SERVICES=(identity care medicine schedule-dose notification gamification)
declare -A PORTS=( [identity]=3001 [care]=3002 [medicine]=3003 [schedule-dose]=3004 [notification]=3005 [gamification]=3006 )
declare -A TAGVAR=( [identity]=MEDO_TAG_IDENTITY [care]=MEDO_TAG_CARE [medicine]=MEDO_TAG_MEDICINE [schedule-dose]=MEDO_TAG_SCHEDULE_DOSE [notification]=MEDO_TAG_NOTIFICATION [gamification]=MEDO_TAG_GAMIFICATION )

[ -f .env ] || { echo "FATAL: .env missing — run scripts/gen-env.py + release.sh"; exit 1; }
for s in "${SERVICES[@]}"; do
  [ -f "secrets/prod/$s.env" ] || { echo "FATAL: secrets/prod/$s.env missing — run scripts/gen-env.py --env prod"; exit 1; }
done

# snapshot currently-running image tags -> .last-good.env (rollback target)
snapshot_last_good() {
  : > .last-good.env
  for s in "${SERVICES[@]}"; do
    img=$(docker inspect "medo-$s-1" --format '{{.Config.Image}}' 2>/dev/null || true)
    tag=${img##*:}
    if [ -n "$img" ] && [ "$tag" != "$img" ]; then
      echo "${TAGVAR[$s]}=$tag" >> .last-good.env
    fi
  done
}

restore_last_good() {
  [ -s .last-good.env ] || return 1
  cp .env .env.failed
  # .last-good.env holds "VAR=tag" lines; rewrite matching MEDO_TAG_* values in .env
  awk 'NR==FNR{ split($0,a,"="); tag[a[1]]=a[2]; next }
       /^MEDO_TAG_/{ split($0,b,"="); if (b[1] in tag){ print b[1] "=" tag[b[1]]; next } }
       { print }' .last-good.env .env.failed > .env.new \
    && mv .env.new .env && rm -f .env.failed && chmod 600 .env
}

NO_PULL=0
[ "${1:-}" = "--no-pull" ] && NO_PULL=1

snapshot_last_good

if [ "$NO_PULL" -eq 0 ]; then
  echo "== docker compose pull"
  "${COMPOSE[@]}" pull
fi

echo "== docker compose up -d"
"${COMPOSE[@]}" up -d

rollback() {
  echo "!! health gate FAILED — rolling back"
  if restore_last_good; then
    echo "== rollback: restoring .last-good tags and restarting"
    "${COMPOSE[@]}" up -d
    echo "!! rolled back to previous release"
  else
    echo "!! no .last-good snapshot — cannot auto-rollback; investigate: docker compose -f compose.yaml logs"
  fi
  exit 1
}

# --- gate 1: /health on every service via published localhost ports (<=60s) ---
echo "== health gate: /health x6 (<=60s)"
deadline=$((SECONDS + 60))
while [ $SECONDS -lt $deadline ]; do
  all_ok=1
  for s in "${SERVICES[@]}"; do
    curl -sf --max-time 2 "http://127.0.0.1:${PORTS[$s]}/health" >/dev/null || all_ok=0
  done
  [ "$all_ok" -eq 1 ] && break
  sleep 2
done
[ "${all_ok:-0}" -eq 1 ] || rollback

# --- gate 2: /ready on every service (service-JWT, minted inside identity) ---
# copied into /app so `import "jose"` resolves against the app's node_modules
echo "== readiness gate: /ready x6"
"${COMPOSE[@]}" cp scripts/ready-check.mjs identity:/app/ready-check.mjs
"${COMPOSE[@]}" exec -T identity node /app/ready-check.mjs || rollback
"${COMPOSE[@]}" exec -T identity rm -f /app/ready-check.mjs || true

# --- gate 3: Caddy public liveness (https, cert-tolerant) ---
echo "== caddy gate: https://api.simmaps.com/health"
caddy_ok=0
for _ in $(seq 1 15); do
  if curl -sfk --max-time 5 --resolve "api.simmaps.com:443:127.0.0.1" "https://api.simmaps.com/health" >/dev/null; then
    caddy_ok=1; break
  fi
  sleep 2
done
[ "$caddy_ok" -eq 1 ] || rollback

# success: current tags become last-good
snapshot_last_good
echo "== deploy OK — tags:"
grep '^MEDO_TAG_' .env
