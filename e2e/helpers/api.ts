// Node-side API + DB helpers for e2e golden paths.
// API base = Caddy https://localhost (self-signed; TLS bypass set in config).
// DB access = docker exec psql into the compose.e2e postgres container.
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const API = process.env.E2E_API_URL ?? "https://localhost";
const PG_CONTAINER =
  process.env.E2E_PG_CONTAINER ?? "medo-e2e-postgres-1";
const HERE = dirname(fileURLToPath(import.meta.url));
const INFRA_ROOT = join(HERE, "..", "..");

export interface ApiResult {
  status: number;
  body: any;
}

export async function api(
  method: string,
  path: string,
  opts: { token?: string; body?: unknown } = {},
): Promise<ApiResult> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  if (opts.token) headers["authorization"] = `Bearer ${opts.token}`;
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { _raw: text.slice(0, 200) };
  }
  return { status: res.status, body };
}

export function must(res: ApiResult, statuses: number[] = [200]): any {
  if (!statuses.includes(res.status)) {
    throw new Error(
      `expected ${statuses} got ${res.status}: ${JSON.stringify(res.body)}`,
    );
  }
  return res.body;
}

// ---------- deterministic data ----------

let counter = 0;
/** Unique-per-run deterministic identity: same seed inputs → same flow. */
export function uniqueEmail(tag: string): string {
  counter += 1;
  return `e2e-${tag}-${Date.now()}-${counter}@medo.test`;
}
export const E2E_PASSWORD = "E2e-Test-Passw0rd!";

export async function signup(
  email: string,
  role: "Patient" | "Caregiver" = "Patient",
  name = "E2E User",
): Promise<{ userId: string }> {
  const res = await api("POST", "/v1/auth/signup", {
    body: { name, email, password: E2E_PASSWORD, role },
  });
  return must(res, [201]);
}

export async function login(
  email: string,
  password = E2E_PASSWORD,
): Promise<{ accessToken: string; userId: string }> {
  const res = await api("POST", "/v1/auth/login", {
    body: { email, password },
  });
  const body = must(res, [200]);
  return { accessToken: body.accessToken, userId: body.userId };
}

/** Full account setup: signup → psql email_verified flip → login token. */
export async function provisionUser(
  tag: string,
  role: "Patient" | "Caregiver" = "Patient",
  name = "E2E User",
  email?: string,
): Promise<{ email: string; userId: string; token: string }> {
  const mail = email ?? uniqueEmail(tag);
  const { userId } = await signup(mail, role, name);
  verifyEmailDb(mail);
  const { accessToken } = await login(mail);
  return { email: mail, userId, token: accessToken };
}

// ---------- postgres (docker exec) ----------

export function psql(db: string, sql: string): string {
  return execFileSync(
    "docker",
    [
      "exec",
      PG_CONTAINER,
      "psql",
      "-U",
      "postgres",
      "-d",
      db,
      "-v",
      "ON_ERROR_STOP=1",
      "-tA",
      "-c",
      sql,
    ],
    { encoding: "utf8" },
  ).trim();
}

/** Verification email is not receivable in e2e — flip the flag (smoke.py parity). */
export function verifyEmailDb(email: string): void {
  psql(
    "identity_db",
    `UPDATE users SET email_verified=true WHERE email='${email}';`,
  );
}

// ---------- medicine ----------

export const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

export async function createCatalogEntry(
  token: string,
  brandName: string,
): Promise<string> {
  const res = await api("POST", "/v1/medicine-catalog", {
    token,
    body: {
      brandName,
      ingredientNames: ["e2e-inet"],
      form: "tablet",
      packagingQuantity: 10,
    },
  });
  return must(res, [200, 201]).id;
}

export async function uploadCatalogPhoto(
  token: string,
  entryId: string,
  slot: "A" | "B" | "C" = "A",
): Promise<void> {
  const issued = must(
    await api("POST", `/v1/medicine-catalog/${entryId}/photos`, {
      token,
      body: { slot },
    }),
    [200, 201],
  );
  const put = await fetch(issued.uploadUrl, {
    method: "PUT",
    headers: { "content-type": "image/png" },
    body: PNG_1PX,
  });
  if (!put.ok) throw new Error(`photo PUT failed: ${put.status}`);
  must(
    await api("PUT", `/v1/medicine-catalog/${entryId}/photos/${slot}`, {
      token,
      body: { photoKey: issued.photoKey },
    }),
    [200],
  );
}

export async function createMedicine(
  token: string,
  patientId: string,
  opts: {
    catalogEntryId?: string;
    brandName?: string;
    withPhoto?: boolean;
    dosesRemaining?: number;
    refillThreshold?: number;
    dosage?: string;
  } = {},
): Promise<{ medicineId: string; catalogEntryId: string }> {
  let catalogEntryId = opts.catalogEntryId;
  if (!catalogEntryId) {
    catalogEntryId = await createCatalogEntry(
      token,
      opts.brandName ?? `E2E-Med-${Date.now()}`,
    );
    if (opts.withPhoto !== false) {
      await uploadCatalogPhoto(token, catalogEntryId, "A");
    }
  }
  const res = await api("POST", "/v1/medicines", {
    token,
    body: {
      patientId,
      catalogEntryId,
      prescribingDoctor: "Dr E2E",
      dosage: opts.dosage ?? "1 tablet",
      dosesRemaining: opts.dosesRemaining ?? 30,
      refillThreshold: opts.refillThreshold ?? 6,
      price: 1.5,
      pharmacyName: "E2E Pharmacy",
    },
  });
  const body = must(res, [200, 201]);
  return { medicineId: body.id ?? body.medicineId, catalogEntryId };
}

// ---------- schedule & dose ----------

export interface DoseSeed {
  date: string; // yyyy-mm-dd (schedule-local)
  time: string; // HH:MM
}

/**
 * Deterministic "markable now" dose: scheduled ~20 min ago → server
 * on-time-window (T-30 … T+60). Falls back to 00:00 UTC when the run
 * happens within 20 min after midnight (still on-time-window).
 */
export function doseTimeNowMinus20(): DoseSeed {
  return doseSeedMinutesAgo(20);
}

/** Dose scheduled `minutesAgo` before now (UTC) — inside on-time window. */
export function doseSeedMinutesAgo(minutesAgo: number): DoseSeed {
  const now = new Date();
  const todayUtc = now.toISOString().slice(0, 10);
  const t = new Date(now.getTime() - minutesAgo * 60_000);
  if (t.toISOString().slice(0, 10) === todayUtc) {
    return { date: todayUtc, time: t.toISOString().slice(11, 16) };
  }
  return { date: todayUtc, time: "00:00" };
}

export async function createSchedule(
  token: string,
  patientId: string,
  opts: {
    medicineId: string;
    dates?: string[];
    doseTimes?: string[];
    timezone?: string;
  },
): Promise<{ scheduleId: string }> {
  const seed = doseTimeNowMinus20();
  const res = await api("POST", `/v1/patients/${patientId}/schedules`, {
    token,
    body: {
      medicineId: opts.medicineId,
      recurrence: {
        kind: "date-list",
        dates: opts.dates ?? [seed.date],
      },
      doseTimes: opts.doseTimes ?? [seed.time],
      timezone: opts.timezone ?? "UTC",
    },
  });
  const body = must(res, [200, 201]);
  return { scheduleId: body.id };
}

export async function listDoses(
  token: string,
  patientId: string,
  from: string,
  to: string,
): Promise<any[]> {
  const res = await api(
    "GET",
    `/v1/patients/${patientId}/doses?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    { token },
  );
  const body = must(res, [200]);
  return body.doses ?? body.items ?? [];
}

export async function getDose(token: string, doseId: string): Promise<any> {
  return must(await api("GET", `/v1/doses/${doseId}`, { token }), [200]);
}

export async function markOutcome(
  token: string,
  doseId: string,
  outcome: "taken-on-time" | "taken-late" | "skipped",
): Promise<any> {
  return must(
    await api("POST", `/v1/doses/${doseId}/outcome`, {
      token,
      body: { outcome },
    }),
    [200, 201, 204],
  );
}

/** Today's dose window covering yesterday→tomorrow (matches frontend fanout). */
export function doseWindow(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getTime() - 2 * 86_400_000)
    .toISOString()
    .slice(0, 10);
  const to = new Date(now.getTime() + 86_400_000).toISOString().slice(0, 10);
  return {
    from: `${from}T00:00:00.000Z`,
    to: `${to}T23:59:59.999Z`,
  };
}

// ---------- gamification ----------

export async function getGamification(
  token: string,
  patientId: string,
): Promise<{ harmonyPoints: number; themeState: string }> {
  return must(
    await api("GET", `/v1/patients/${patientId}/gamification`, { token }),
    [200],
  );
}

// ---------- care ----------

export async function createInvite(
  token: string,
  caregiverEmail: string,
): Promise<string> {
  const res = await api("POST", "/v1/care/links/invites", {
    token,
    body: { caregiverEmail },
  });
  return must(res, [200, 201]).inviteId;
}

/** LD-CARE-02: token = base64url(HMAC-SHA256(inviteId, INVITE_TOKEN_SECRET)). */
export function inviteToken(inviteId: string): string {
  const env = readFileSync(join(INFRA_ROOT, "secrets", "dev", "care.env"), "utf8");
  const secret = env.match(/^INVITE_TOKEN_SECRET=(.+)$/m)?.[1]?.trim();
  if (!secret) throw new Error("INVITE_TOKEN_SECRET not found in care.env");
  return createHmac("sha256", secret).update(inviteId).digest("base64url");
}

export async function acceptInvite(
  caregiverToken: string,
  rawToken: string,
): Promise<void> {
  must(
    await api("POST", `/v1/care/invites/${rawToken}/accept`, {
      token: caregiverToken,
    }),
    [200, 201, 204],
  );
}

export async function listLinks(token: string): Promise<any[]> {
  const res = await api("GET", "/v1/care/links", { token });
  return must(res, [200]).links ?? [];
}

export async function endLink(token: string, linkId: string): Promise<void> {
  must(await api("POST", `/v1/care/links/${linkId}/end`, { token }), [
    200, 201, 204,
  ]);
}

// ---------- notifications ----------

export async function listFeed(token: string): Promise<any[]> {
  const res = await api("GET", "/v1/notifications?limit=50", { token });
  return must(res, [200]).items ?? [];
}

// ---------- account ----------

export async function deleteMe(token: string): Promise<ApiResult> {
  return api("DELETE", "/v1/me", { token });
}
