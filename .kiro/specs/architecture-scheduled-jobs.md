# Scheduled Jobs Inventory

Complete inventory of embedded scheduled/background jobs across the 6 Medo backend services. Decided in Map 4 ticket 02 (2026-11-21). Service PRDs cite this document and list only per-service deltas — they never restate this inventory.

Pattern (Map 3 t01): embedded `node-cron` jobs inside each service — no worker/scheduler service. All times UTC unless noted. Every job is a stateless tick: failure = log + Sentry event + next tick retries; no job carries critical unrecoverable state.

## Schedule & Dose Service

| Job | Cadence | Purpose | Mechanism |
|---|---|---|---|
| `dose-generation` | Daily `03:00 UTC` | Extend materialized Dose rows to rolling `today + 90d` horizon per Schedule tz; picks up edits/regeneration | DB scan of active Schedules |
| `missed-lock-tick` | Every minute | For each active Schedule, detect local-date advance in schedule tz → lock prior day's unmarked doses as `missed`, emit `DoseOutcomeChanged` per dose | DB scan of active Schedules + per-schedule local-time computation |

Notes:
- Initial dose materialization is **synchronous** on `POST/PATCH /v1/patients/{id}/schedules` — the daily job only maintains the rolling edge.
- Missed-lock precision = ≤60s after schedule-local midnight (tick boundary); the midnight missed ping follows via Notification's per-minute poll.

## Notification Service

One `node-cron` scheduler, four named tasks:

| Job | Cadence | Purpose | Mechanism |
|---|---|---|---|
| `reminder-email-tick` | Every minute | `GET /v1/doses/due` on Schedule & Dose → Web Push for T−30/T/T+1hr/hourly reminder windows; same response data evaluates email fallback (one email at T+1hr if unmarked + one at midnight missed, max 2/dose) | Internal REST pull |
| `feed-retention` | Daily `04:00 UTC` | Purge feed rows: 90d unread / 30d after read | DB scan own `notification_db` |
| `push-orphan-purge` | Weekly `Sun 04:30 UTC` | Purge push subscriptions whose user no longer exists | DB scan own `notification_db` |
| `broker-watchdog` | Daily `05:00 UTC` | Count `broker_db.dead_letters` + total outbox backlog → Sentry event on non-zero/threshold; purge dead letters older than 30d | DB scan `broker_db` |

Notes:
- Web Push 404/410 subscription pruning happens inline at send time (resilience matrix), not in a job.
- `broker-watchdog` is the single platform watchdog — sole writer for dead-letter purge, no races.

## Care Service

| Job | Cadence | Purpose | Mechanism |
|---|---|---|---|
| `invite-expiry-sweep` | Hourly at `:07` | Mark invites with `expiresAt <= now` as expired, emit `CareLinkInviteExpired` once per invite (idempotent via status transition) | DB scan own `care_db` |

## Identity Service

| Job | Cadence | Purpose | Mechanism |
|---|---|---|---|
| `auth-cleanup` | Daily `04:30 UTC` | Purge expired verify/reset tokens (TTL expiry) + expired/revoked sessions and refresh tokens | DB scan own `identity_db` |

Notes: login-failure cooldown (25min) and sliding refresh are timestamp checks at request time — no job.

## Medicine Service

**No scheduled jobs.** All behavior is request-driven or event-driven (`RefillThresholdCrossed` emission on Doses Remaining change).

## Gamification Service

**No scheduled jobs.** Points/theme update on every `DoseOutcomeChanged` event; pull-bootstrap on gap.

## Platform-level (not a service)

| Job | Owner | Cadence | Purpose |
|---|---|---|---|
| Outbox row deletion after publish | `@medo/eventing` publisher (inline, per service) | continuous | Outbox hygiene — not a cron job |
| Dead-letter purge (>30d post-replay) | Notification `broker-watchdog` | daily `05:00 UTC` | Retention enforcement |

## PRD obligations

Each service PRD lists only its jobs from this table (name, cadence, purpose, failure behavior = stateless tick + Sentry). Services marked "no jobs" state it explicitly. No PRD invents jobs beyond this inventory without reopening this decision.
