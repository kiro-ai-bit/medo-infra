# Platform Quality Baseline

Uniform quality baseline for all 6 Medo backend services + frontend + embedded jobs. Decided in Map 4 ticket 01 (2026-11-21). Service PRDs reference this document and list only per-service deltas — they never restate these conventions.

## Load envelope

Expected load ceilings (sanity-check numbers, not capacity planning):

- Concurrent users: **< 50**
- Dose events/day (reminders + outcomes): **< 5,000**
- Medicine catalog entries: **< 10,000**
- Deployment: single instance per service on one EC2 `t3.micro` — sizing assumes this envelope.

## Latency targets

p95 response-time targets per route class:

| Route class | p95 target |
|---|---|
| Public reads (dose lists, medicine lists, gamification, feeds) | < 300 ms |
| Public writes (dose outcome, medicine save, link actions) | < 500 ms |
| Internal service calls (check-link, `/doses/due` polls, directory lookups) | < 200 ms |

Measured at the service boundary (Fastify response time); gateway/proxy overhead excluded.

## Availability & reliability

- **Availability target: ~99%** during the hackathon/demo period — no enterprise SLA; honest for a single small server.
- **Fail cleanly:** a failed dependency returns a clear error (4xx/5xx JSON), never a crash or hang.
- **Degrade where cheap:** non-critical reads may degrade gracefully (e.g., gamification read fails → Today screen renders without score).
- **No silent data loss:** writes either commit or fail cleanly; no partial state.

## Resilience defaults

Per dependency type — timeout, retry, failure mode:

| Dependency | Timeout | Retry | On failure |
|---|---|---|---|
| Own Postgres DB | 5 s | none (fast-fail) | fail-closed — return 503 |
| Internal REST (check-link, `/doses/due`, directory) | 3 s | 1 retry, 200 ms backoff | fail-closed for authz (deny); Care check-link 15 s positive cache is the buffer |
| Event consumer | n/a (polling) | 5 attempts → `dead_letters` (Map 3 t07) | unchanged |
| Resend (email) | 10 s | 2 retries, exp. backoff | fail-open — log + Sentry event; feed row still recorded |
| Web Push | 10 s | 2 retries | fail-open + prune subscription on 404/410 |
| R2 / S3 (object storage) | 10 s | 2 retries | fail-closed for attach-confirm; presigned URL generation is local |

**Idempotency:** every retryable write command (dose outcome, medicine save, link actions) must be safe to retry — idempotency key or natural idempotency (last-write-wins on outcomes).

## Data retention

| Data | Retention | Enforcement |
|---|---|---|
| Verify/reset tokens | TTL expiry (60 min reset / 24 h verify) | Identity embedded cleanup job |
| Sessions / refresh tokens | Until logout/revoke/reset; sliding 30 d; expired+revoked purged daily | Identity embedded cleanup job |
| Push subscriptions | Until unsubscribe / 404-410 prune; orphans purged weekly | Notification embedded job |
| Notification feed | 90 d unread / 30 d after read | Notification embedded job |
| Outbox rows | Deleted after publish | `@medo/eventing` publisher |
| Dead letters | Kept until manual replay + 30 d, then purge | `@medo/eventing` cleanup |
| Backups | **None in v1** — accepted risk at hackathon scale | stated explicitly |
| Dose outcomes, points, medicines | Account lifetime; purged on `AccountDeleted` | each service's event consumer |

## PRD obligations

Each service PRD must specify only:

- Its dependency list mapped onto the resilience matrix (any deviation with justification).
- Its `/ready` dependency checks (per observability baseline).
- Any retention rows it owns beyond the table above.
- Per-route-class latency notes where a route class doesn't apply or needs a tighter bound.
