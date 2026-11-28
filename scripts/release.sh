#!/usr/bin/env bash
# Medo release — run from workstation (Git Bash) inside medo-infra.
# Builds each backend service image at its repo HEAD, pushes SHA-tagged
# images to GHCR, updates .env MEDO_TAG_*, regenerates prod env files,
# ships the infra dir to EC2, then runs deploy.sh there.
#
#   bash scripts/release.sh            # build+push all + deploy
#   bash scripts/release.sh --build-only   # build+push, no deploy
#
# Env overrides: MEDO_HOST, MEDO_SSH_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${MEDO_HOST:-ubuntu@52.63.127.50}"
KEY="${MEDO_SSH_KEY:-/d/medo/AppHub/.secrets/medo-prod-key.pem}"
GITHUB_PAT="${GITHUB_PAT:-$(grep '^GITHUB_PAT=' /d/medo/.env | cut -d= -f2-)}"
export GITHUB_PAT
SERVICES=(identity care medicine schedule-dose notification gamification)
BUILD_ONLY=0
[ "${1:-}" = "--build-only" ] && BUILD_ONLY=1

command -v docker >/dev/null || { echo "FATAL: docker not found"; exit 1; }
[ -n "$GITHUB_PAT" ] || { echo "FATAL: GITHUB_PAT empty"; exit 1; }

echo "== ghcr login (kiro-ai-bit)"
echo "$GITHUB_PAT" | docker login ghcr.io -u kiro-ai-bit --password-stdin

for s in "${SERVICES[@]}"; do
  repo="../medo-$s"
  [ -d "$repo" ] || { echo "FATAL: $repo missing (AppHub sibling layout required)"; exit 1; }
  # image tag = repo HEAD sha; refuse to mislabel a dirty working tree
  if [ -n "$(git -C "$repo" status --porcelain)" ]; then
    echo "FATAL: $repo has uncommitted changes — commit first so sha-$sha tags are honest"
    exit 1
  fi
  sha=$(git -C "$repo" rev-parse --short=12 HEAD)
  tag="sha-$sha"
  img="ghcr.io/kiro-ai-bit/medo-$s:$tag"
  echo "=== build $img  (context $repo)"
  docker build --secret id=github_pat,env=GITHUB_PAT -t "$img" "$repo"
  docker push "$img"
  var="MEDO_TAG_$(echo "$s" | tr 'a-z-' 'A-Z_')"
  if grep -q "^${var}=" .env 2>/dev/null; then
    sed -i "s|^${var}=.*|${var}=${tag}|" .env
  else
    echo "${var}=${tag}" >> .env
  fi
done

echo "== regenerate prod env files"
python scripts/gen-env.py --env prod

[ "$BUILD_ONLY" -eq 1 ] && { echo "== build-only done"; exit 0; }

echo "== ship infra -> $HOST:/opt/medo"
tar czf - \
  --exclude=.git \
  --exclude='secrets/dev' \
  --exclude='.last-good.env' \
  . | ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" \
    'mkdir -p /opt/medo && tar xzf - -C /opt/medo && chmod 600 /opt/medo/secrets/prod/*.env /opt/medo/.env'

echo "== remote deploy"
ssh -i "$KEY" "$HOST" 'cd /opt/medo && bash scripts/deploy.sh'
