import { expect, test } from "@playwright/test";
import { api, E2E_PASSWORD, login, must, uniqueEmail, verifyEmailDb } from "../helpers/api.js";
import { uiLogin, uiSignup } from "../helpers/ui.js";

// Golden path 1 — patient signup → verify gate → login → app shell.

test("patient signup, email-verify gate, login, reach Today", async ({
  page,
}) => {
  const email = uniqueEmail("auth");
  const name = "E2E Patient One";

  // Signup through the real UI.
  await uiSignup(page, { name, email, role: "Patient" });
  await page.getByRole("button", { name: "Go to login" }).click();
  await expect(page).toHaveURL(/\/login/);

  // Login before verification → enumeration-safe unverified gate.
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(
    page.getByText("Your email is not verified yet."),
  ).toBeVisible();

  // Verify (DB flip — no mailbox in e2e), then login succeeds.
  verifyEmailDb(email);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL(/\/today/, { timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "Today", exact: true }),
  ).toBeVisible();

  // Complete the profile: PATCH /v1/me is the profile path (no profile-edit
  // UI exists — signup seeds the row, PATCH sets displayName/timezone).
  const session = await login(email);
  const me = must(
    await api("PATCH", "/v1/me", {
      token: session.accessToken,
      body: { displayName: name, timezone: "UTC" },
    }),
  );
  expect(me.displayName).toBe(name);
  expect(me.timezone).toBe("UTC");

  // Reload proves session persistence via the
  // host-only SameSite=Lax refresh cookie (cross-origin https app↔api).
  await page.reload();
  await expect(page).toHaveURL(/\/today/, { timeout: 30_000 });
});

test("login API returns profile fields for a provisioned user", async () => {
  const email = uniqueEmail("auth-api");
  const { userId } = await api("POST", "/v1/auth/signup", {
    body: {
      name: "E2E API User",
      email,
      password: E2E_PASSWORD,
      role: "Patient",
    },
  }).then((r) => must(r, [201]));
  verifyEmailDb(email);
  const session = await login(email);
  expect(session.userId).toBe(userId);
  const me = must(await api("GET", "/v1/me", { token: session.accessToken }));
  expect(me.email).toBe(email);
  expect(me.role).toBe("Patient");
});
