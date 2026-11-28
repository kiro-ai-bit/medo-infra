import { expect, test } from "@playwright/test";
import {
  createMedicine,
  createSchedule,
  doseTimeNowMinus20,
  doseWindow,
  listDoses,
  PNG_1PX,
  provisionUser,
} from "../helpers/api.js";
import { uiLogin } from "../helpers/ui.js";

// Golden path 2 — catalog entry + photo → patient medicine → schedule →
// dose materializes onto Today. Catalog/photo/schedule driven through the UI;
// account provisioning via API for determinism.

test("create medicine with photo, schedule, dose appears on Today", async ({
  page,
}) => {
  const patient = await provisionUser("med");
  const brand = `E2E-Tab-${Date.now()}`;
  const seed = doseTimeNowMinus20();

  await uiLogin(page, patient.email);

  // --- catalog entry via UI ---
  await page.goto("/medicines/new");
  await page.getByRole("button", { name: "New entry" }).click();
  await page.locator("#brand").fill(brand);
  await page.locator("#ing").fill("e2e-inet");
  await page.locator("#pack").fill("10");
  await page.getByRole("button", { name: "Create entry" }).click();
  await expect(page.getByRole("heading", { name: brand })).toBeVisible();

  // --- slot-A photo upload via UI (presigned PUT → R2 → confirm) ---
  const slotA = page
    .locator("label", { hasText: "Outer packaging" })
    .locator('input[type="file"]');
  await slotA.setInputFiles({
    name: "packaging.png",
    mimeType: "image/png",
    buffer: PNG_1PX,
  });
  await expect(page.getByText("Slot A uploaded.")).toBeVisible({
    timeout: 30_000,
  });

  // --- patient medicine details via UI ---
  await page.locator("#prescribingDoctor").fill("Dr E2E");
  await page.locator("#dosage").fill("1 tablet");
  await page.locator("#dosesRemaining").fill("30");
  await page.locator("#refillThreshold").fill("6");
  await page.locator("#price").fill("1.50");
  await page.locator("#pharmacyName").fill("E2E Pharmacy");
  await page.getByRole("button", { name: "Add medicine" }).click();
  await expect(page).toHaveURL(/\/medicines$/, { timeout: 30_000 });
  await expect(page.getByText(brand).first()).toBeVisible();

  // --- schedule via UI: once, today, dose time ~20 min ago (UTC) ---
  await page.goto("/schedules/new");
  // Option label is "{brandName} — {dosage}" and brandName case is normalized
  // server-side — match by value via case-insensitive text scan.
  const medSelect = page.locator("#med");
  const medValue = await medSelect.evaluate(
    (el, needle) => {
      const opt = Array.from((el as HTMLSelectElement).options).find((o) =>
        o.text.toLowerCase().includes(needle),
      );
      return opt?.value ?? null;
    },
    brand.toLowerCase(),
  );
  expect(medValue).toBeTruthy();
  await medSelect.selectOption(medValue!);
  await page.locator("#kind").selectOption("once");
  await page.locator("#dates").fill(seed.date);
  await page.locator("#times").fill(seed.time);
  await page.locator("#tz").fill("UTC");
  await page.getByRole("button", { name: "Create schedule" }).click();
  await expect(page).toHaveURL(/\/schedules\//, { timeout: 30_000 });

  // --- dose materialized synchronously → Today card ---
  await page.goto("/today");
  const card = page.locator("li[data-dose-id]", { hasText: brand });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByRole("button", { name: "Taken" })).toBeVisible();

  // API-side proof the dose exists server-side too.
  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses.length).toBeGreaterThanOrEqual(1);
});

test("API-seeded schedule materializes a dose synchronously", async () => {
  const patient = await provisionUser("seed");
  const { medicineId } = await createMedicine(patient.token, patient.userId, {
    brandName: `E2E-Seed-${Date.now()}`,
  });
  const { scheduleId } = await createSchedule(
    patient.token,
    patient.userId,
    { medicineId },
  );
  expect(scheduleId).toBeTruthy();
  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses).toHaveLength(1);
  expect(doses[0].outcome).toBe("unmarked");
});
