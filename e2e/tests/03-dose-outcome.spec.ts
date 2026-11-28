import { expect, test } from "@playwright/test";
import {
  createMedicine,
  createSchedule,
  doseWindow,
  getDose,
  getGamification,
  listDoses,
  markOutcome,
  provisionUser,
} from "../helpers/api.js";
import { uiLogin } from "../helpers/ui.js";

// Golden path 3 — mark dose taken → outcome persisted → Harmony Points +
// theme update via the DoseOutcomeChanged → gamification consumer chain.

test("mark dose taken updates badge and harmony points", async ({ page }) => {
  const patient = await provisionUser("dose");
  const brand = `E2E-Out-${Date.now()}`;
  const { medicineId } = await createMedicine(patient.token, patient.userId, {
    brandName: brand,
    dosesRemaining: 30,
    refillThreshold: 6,
  });
  await createSchedule(patient.token, patient.userId, { medicineId });

  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses).toHaveLength(1);
  const doseId = doses[0].id;

  // Baseline: no outcomes yet → synthesized {0, Harmony}.
  const before = await getGamification(patient.token, patient.userId);
  expect(before.harmonyPoints).toBe(0);

  await uiLogin(page, patient.email);
  const card = page.locator("li[data-dose-id]", { hasText: brand });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await card.getByRole("button", { name: "Taken" }).click();

  // Badge flips to the marked outcome label.
  await expect(card.getByTestId("window-badge")).toHaveText("Taken on time", {
    timeout: 30_000,
  });
  await expect(card.getByRole("button", { name: "Taken" })).toHaveCount(0);

  // Server outcome persisted.
  await expect
    .poll(async () => (await getDose(patient.token, doseId)).outcome, {
      timeout: 30_000,
    })
    .toBe("taken-on-time");

  // Event chain: outbox → broker → gamification consumer (5s poll) → +10.
  await expect
    .poll(
      async () => {
        const g = await getGamification(patient.token, patient.userId);
        return `${g.harmonyPoints}|${g.themeState}`;
      },
      { timeout: 90_000, intervals: [2_000, 5_000] },
    )
    .toBe("10|Harmony");

  // Widget reflects the same state. Gamification updates asynchronously via
  // the event chain (after the mark mutation's invalidate), so reload to
  // force a fresh fetch rather than asserting on the stale cache.
  await page.reload();
  await expect(page.getByTestId("harmony-points")).toHaveText("10 pts", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("theme-state")).toHaveText("Harmony");
});
