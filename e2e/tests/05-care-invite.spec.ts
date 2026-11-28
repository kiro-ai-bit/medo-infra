import { expect, test } from "@playwright/test";
import {
  createInvite,
  createMedicine,
  createSchedule,
  doseWindow,
  getDose,
  inviteToken,
  listDoses,
  listLinks,
  provisionUser,
  uniqueEmail,
} from "../helpers/api.js";
import { E2E_PASSWORD } from "../helpers/api.js";

const APP_URL = process.env.E2E_APP_URL ?? "https://localhost:3000";

// Golden path 5 — patient invites caregiver → caregiver accepts via the
// token link → caregiver marks the patient's dose (actor attribution).

test("care invite, caregiver accept, caregiver marks dose", async ({
  browser,
}) => {
  // Patient + dose seeded via API.
  const patient = await provisionUser("pat", "Patient", "E2E Patient Pat");
  const caregiverEmail = uniqueEmail("cg");
  const { medicineId } = await createMedicine(
    patient.token,
    patient.userId,
    { brandName: `E2E-Care-${Date.now()}` },
  );
  await createSchedule(patient.token, patient.userId, { medicineId });
  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses.length).toBeGreaterThanOrEqual(1);
  const doseId = doses[0].id;

  // Patient creates the invite (API — link itself only travels by email).
  const inviteId = await createInvite(patient.token, caregiverEmail);
  const rawToken = inviteToken(inviteId);

  // Caregiver account with the invited email.
  const caregiver = await provisionUser(
    "cg",
    "Caregiver",
    "E2E Caregiver",
    caregiverEmail,
  );

  // UI: caregiver opens the invite link → Accept.
  const cgContext = await browser.newContext({
    baseURL: undefined,
    ignoreHTTPSErrors: true,
    timezoneId: "UTC",
    locale: "en-US",
  });
  const cgPage = await cgContext.newPage();
  try {
    await cgPage.goto(`${APP_URL}/invite/${rawToken}`);
    await expect(
      cgPage.getByText(/invited you to help manage/),
    ).toBeVisible({ timeout: 30_000 });
    // Not authenticated in this fresh context → login carrying next=.
    await cgPage.getByRole("link", { name: "Log in" }).click();
    await expect(cgPage).toHaveURL(/\/login\?next=/);
    await cgPage.locator("#email").fill(caregiverEmail);
    await cgPage.locator("#password").fill(E2E_PASSWORD);
    await cgPage
      .getByRole("button", { name: "Log in", exact: true })
      .click();
    // Login returns to the invite landing → accept. The guest-guard on /login
    // races router.replace(next) — if it wins we land on /today; re-navigate.
    await expect(cgPage).not.toHaveURL(/\/login/, { timeout: 30_000 });
    if (!cgPage.url().includes("/invite/")) {
      await cgPage.goto(`${APP_URL}/invite/${rawToken}`);
    }
    await expect(
      cgPage.getByRole("button", { name: "Accept invite" }),
    ).toBeVisible({ timeout: 30_000 });
    await cgPage
      .getByRole("button", { name: "Accept invite" })
      .click();
    await expect(cgPage.getByTestId("invite-accepted")).toBeVisible({
      timeout: 30_000,
    });

    // Caregiver switches to the patient and marks the dose.
    await cgPage.getByRole("button", { name: "Go to Today" }).click();
    await expect(cgPage).toHaveURL(/\/today/);
    const bar = cgPage.getByTestId("patient-context-bar");
    await expect(bar).toBeVisible({ timeout: 30_000 });
    await bar.locator("select").selectOption({ label: "E2E Patient Pat" });

    const card = cgPage.locator("li[data-dose-id]", {
      hasText: "E2E-Care",
    });
    // brandName appears in card via medicine displayName
    await expect(card.first()).toBeVisible({ timeout: 30_000 });
    await card
      .first()
      .getByRole("button", { name: "Taken" })
      .click();
    await expect(card.first().getByTestId("window-badge")).toHaveText(
      "Taken on time",
      { timeout: 30_000 },
    );
  } finally {
    await cgContext.close();
  }

  // Attribution: server recorded the caregiver as actor.
  await expect
    .poll(async () => (await getDose(patient.token, doseId)).actorId, {
      timeout: 30_000,
    })
    .toBe(caregiver.userId);

  // Link visible to both parties.
  const patientLinks = await listLinks(patient.token);
  const caregiverLinks = await listLinks(caregiver.token);
  expect(patientLinks.length).toBe(1);
  expect(caregiverLinks.length).toBe(1);
  expect(patientLinks[0].linkId).toBe(caregiverLinks[0].linkId);
});
