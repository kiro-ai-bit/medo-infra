# Medo Infra — Docker Compose stacks + Caddy gateway + deploy tooling

Owns all Docker Compose for Medo (Map 5 t02, ticket 31). Service source lives in the
sibling `AppHub/medo-*` repos; this repo owns orchestration only — no service source
on any host.

## Layout

| Path | Purpose |
|------|---------|
| `compose.yaml` | Prod stack — 6 services + Postgres + Caddy; GHCR SHA-tagged images |
| `compose.dev.yaml` | Dev stack — builds images from sibling repos, Caddy on `http://localhost:8080` |
| `compose.e2e.yaml` | E2E overlay (ticket 32) — adds frontend, Caddy `https://localhost` |
| `Caddyfile` | Public-route table: unlisted = 404; CORS; JWT pass-through |
| `postgres/init/` | First-boot init: 7 roles + 7 DBs (`*_db` + `broker_db`) |
| `scripts/gen-env.py` | Generates `.env` + `secrets/<env>/*.env` from `AppHub/.secrets` |
| `scripts/release.sh` | Workstation: build+push GHCR SHA images → ship → remote deploy |
| `scripts/deploy.sh` | Host: pull → up → health/ready/caddy gates → `.last-good` rollback |
| `scripts/ready-check.mjs` | `/ready` gate (service-JWT minted inside identity container) |
| `scripts/smoke.py` | Full-stack smoke: signup→verify→login→medicine→schedule→dose |
| `scripts/gen-seed-assets.py` | Generates showcase medicine photos → `scripts/seed-assets/` |
| `scripts/seed-showcase.py` | Idempotent Kiroween showcase seeder (accounts, meds, schedules, dose history) |

## Quick start (dev)

```bash
# one-time per shell: GitHub Packages auth for @kiro-ai-bit/* installs
export GITHUB_PAT=<classic PAT with read:packages>

python scripts/gen-env.py --env dev
GITHUB_PAT=$GITHUB_PAT docker compose -f compose.dev.yaml --env-file .env up -d --build
```

API gateway: `http://localhost:8080` (plain HTTP — the `Secure` refresh cookie is
rejected by browsers on http; use curl or the e2e https profile for browser flows).
Service ports are also published on `127.0.0.1:3001..3006` for debugging.

## Prod deploy

```bash
bash scripts/release.sh           # build+push all images, ship, deploy
bash scripts/release.sh --build-only
```

`release.sh` builds each `AppHub/medo-<svc>` repo at HEAD →
`ghcr.io/kiro-ai-bit/medo-<svc>:sha-<short12>` → tar|ssh to
`ubuntu@52.63.127.50:/opt/medo` → runs `deploy.sh` there.

`deploy.sh` gates: `/health` ×6 (≤60s) → `/ready` ×6 (service-JWT) →
`https://api.simmaps.com/health` via Caddy. On failure it restores
`.last-good.env` tags and restarts. First deploy has no rollback target.

DB migrations run automatically at service boot (drizzle migrate). Rollback is
app-code only — migrations are forward-only.

The frontend is NOT part of this stack: prod hosting is Vercel
(`medo-frontend` project, git-connected to `kiro-ai-bit/medo-frontend`,
`app.simmaps.com`); `compose.e2e.yaml` builds a local image for Playwright only.

## Smoke test

```bash
python scripts/smoke.py https://api.simmaps.com \
  --psql "docker exec medo-postgres-1 psql -U postgres -d identity_db"
```

`--psql` flips `email_verified` (no mailbox in smoke). Without it the script
still runs and reports the expected login 403. Route-table assertions verify
internal paths (`/v1/doses/due`, `/v1/care/check-link`, `/v1/users/*`,
`/metrics`, `/ready`, `/v1/patients/*/has-dose-records`) return 404 externally.

## Secrets

- `.env` + `secrets/<env>/*.env` are generated, gitignored, mode 600 on host.
- Source of truth: `AppHub/.secrets/*.json` locally, SSM `/medo/prod/*` in AWS.
- Re-run `gen-env.py` after any secret rotation; never commit env files.
- GHCR pull on host: images under `ghcr.io/kiro-ai-bit/` — if packages are
  private, run `docker login ghcr.io` once on the host (PAT `read:packages`).
