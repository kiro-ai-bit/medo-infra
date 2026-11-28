import { expect, test } from "@playwright/test";
import {
  createMedicine,
  createSchedule,
  doseWindow,
  getDose,
  listDoses,
  provisionUser,
} from "../helpers/api.js";
import { uiLogin } from "../helpers/ui.js";

// Golden path 7 — offline mark → write-queue enqueue → reconnect → FIFO
// replay syncs the outcome to the server.

test("offline dose mark syncs on reconnect", async ({ page, context }) => {
  const patient = await provisionUser("off");
  const brand = `E2E-Off-${Date.now()}`;
  const { medicineId } = await createMedicine(patient.token, patient.userId, {
    brandName: brand,
  });
  await createSchedule(patient.token, patient.userId, { medicineId });
  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses).toHaveLength(1);
  const doseId = doses[0].id;

  await uiLogin(page, patient.email);
  const card = page.locator("li[data-dose-id]", { hasText: brand });
  await expect(card).toBeVisible({ timeout: 30_000 });

  // Go offline → mark → queued locally, not sent.
  await context.setOffline(true);
  await card.getByRole("button", { name: "Taken" }).click();
  await expect(page.getByTestId("offline-note")).toBeVisible({
    timeout: 15_000,
  });
  // Server still sees the dose unmarked while offline.
  expect((await getDose(patient.token, doseId)).outcome).toBe("unmarked");

  // Reconnect → connectivity proof-clear → queue replay → invalidate.
  await context.setOffline(false);
  await expect
    .poll(async () => (await getDose(patient.token, doseId)).outcome, {
      timeout: 60_000,
      intervals: [2_000, 5_000],
    })
    .toBe("taken-on-time");

  // UI converges to the marked state.
  await expect(card.getByTestId("window-badge")).toHaveText("Taken on time", {
    timeout: 30_000,
  });
});
