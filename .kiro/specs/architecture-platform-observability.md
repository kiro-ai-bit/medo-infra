# Platform Observability Defaults

Uniform observability baseline for all 6 Medo backend services + frontend + embedded jobs. Decided in Map 3 ticket 08 (2026-11-21). Service PRDs reference this document and list only per-service specifics — they never restate these conventions.

## Logging

- Structured JSON logs via **Pino** (Fastify native logger; `logger: true` per service).
- Every log line carries: `service`, `level`, `msg`, plus `requestId` (HTTP) or `eventId` (event consumer) when applicable.
- **Correlation:** `X-Request-Id` header generated at the API gateway, forwarded on internal service calls, and stamped onto events in the `{eventId, occurredAt}` envelope flow. One ID traces a request or event across services.
- No distributed tracing (OpenTelemetry rejected — grep-able correlated logs suffice at this scale).

## Metrics

- Each service exposes `GET /metrics` (Prometheus text format, internal route — service-JWT gated).
- Fixed metric set per service: RED per HTTP route (rate, errors, duration histogram) + service-specific counters.
- Required service-specific counters: outbox backlog depth, `broker_db.events` lag, `broker_db.dead_letters` count, clock-job run success/fail, push-send success/fail (Notification).
- No Prometheus/Grafana server — scrape via `curl`/manual during incidents.

## Error tracking

- **Sentry free tier** (developer plan). One Sentry project per service + one for frontend (`@sentry/nextjs`).
- `@sentry/node` SDK, ~5 lines per service; captures unhandled exceptions with `requestId`/`userId` context. DSN via env (local `.env`) / SSM Parameter Store (prod).
- Alert rules: email on new/regressed errors per project.

## Alerting

Email-only, layered:

1. **Sentry alert rules** — new/regressed errors.
2. **UptimeRobot free tier** — HTTP check on gateway `/health` every 5 min, email on down.
3. **AWS Budget alert $25** — cost guard (ticket 02).
4. **Internal watchdog** — daily node-cron job in one service counts `broker_db.dead_letters` + outbox depth; emits a Sentry event when non-zero/threshold.

No PagerDuty/SMS. On-call = project owner.

## Health endpoints

Uniform per service:

- `GET /health` — liveness; 200 if process up. Public route via gateway; UptimeRobot target.
- `GET /ready` — readiness; 200 only if critical deps respond (own DB ping; `broker_db` ping for publisher/consumer services). Internal route; used by Docker Compose `healthcheck` and deploy scripts.

## PRD obligations

Each service PRD must specify only:

- Its custom `/metrics` counters (beyond the fixed RED set).
- Which deps its `/ready` checks.
- Its Sentry project name/DSN env var.
- Any service-specific log fields beyond the standard set.
