import { expect, test } from "@playwright/test";
import {
  createMedicine,
  createSchedule,
  doseWindow,
  listDoses,
  listFeed,
  markOutcome,
  provisionUser,
} from "../helpers/api.js";
import { uiLogin } from "../helpers/ui.js";

// Golden path 6 — doses-remaining crosses the refill threshold →
// RefillThresholdCrossed → notification feed row surfaces in the UI.

test("refill threshold crossing produces a feed alert", async ({ page }) => {
  const patient = await provisionUser("refill");
  const brand = `E2E-Refill-${Date.now()}`;
  // 7 remaining, alert at ≤6 → one taken dose (count −1) crosses once.
  // NOTE: shared event schema only allows threshold literals 6|0 — a custom
  // threshold (e.g. 1) would emit an event the consumers can't parse.
  const { medicineId } = await createMedicine(patient.token, patient.userId, {
    brandName: brand,
    dosesRemaining: 7,
    refillThreshold: 6,
  });
  await createSchedule(patient.token, patient.userId, { medicineId });

  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses).toHaveLength(1);
  await markOutcome(patient.token, doses[0].id, "taken-on-time");

  // Event chain: DoseOutcomeChanged → medicine consumer (delta + threshold)
  // → RefillThresholdCrossed → notification consumer → feed row (~15-30s).
  await expect
    .poll(
      async () => {
        const feed = await listFeed(patient.token);
        // Catalog brandName is normalized (lowercased) server-side.
        return feed.some(
          (i) =>
            i.type === "refill" &&
            i.title.toLowerCase().includes(brand.toLowerCase()),
        );
      },
      { timeout: 120_000, intervals: [3_000, 5_000] },
    )
    .toBe(true);

  // UI surface: /notifications lists the refill alert.
  await uiLogin(page, patient.email);
  await page.goto("/notifications");
  await expect(
    page.locator("[data-feed-id]", { hasText: `Refill alert: ${brand}` }),
  ).toBeVisible({ timeout: 30_000 });
});
