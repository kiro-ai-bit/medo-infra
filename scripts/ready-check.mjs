// Medo deploy readiness gate — runs INSIDE the identity container
// (docker compose cp + exec). Mints a service JWT (iss=medo-identity,
// aud=medo-<svc>) from SERVICE_PRIVATE_KEY and polls each service's
// service-authenticated /ready endpoint. Exit 0 = all ready.
import { importJWK, SignJWT } from "jose";

const key = JSON.parse(process.env.SERVICE_PRIVATE_KEY);
const priv = await importJWK(key, "ES256");

const services = [
  ["identity", 3001],
  ["care", 3002],
  ["medicine", 3003],
  ["schedule-dose", 3004],
  ["notification", 3005],
  ["gamification", 3006],
];

let failed = 0;
for (const [name, port] of services) {
  const jwt = await new SignJWT({})
    .setProtectedHeader({ alg: "ES256", kid: key.kid })
    .setIssuer("medo-identity")
    .setAudience(`medo-${name}`)
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(priv);
  try {
    const res = await fetch(`http://${name}:${port}/ready`, {
      headers: { authorization: `Bearer ${jwt}` },
      signal: AbortSignal.timeout(5000),
    });
    const body = await res.json().catch(() => ({}));
    const ok = res.ok && body.status === "ready";
    console.log(`${name}: HTTP ${res.status} ${body.status ?? ""}`.trim());
    if (!ok) failed++;
  } catch (err) {
    console.log(`${name}: ERROR ${err.message}`);
    failed++;
  }
}
process.exit(failed ? 1 : 0);
