import { expect, test } from "@playwright/test";
import {
  createMedicine,
  createSchedule,
  doseSeedMinutesAgo,
  doseWindow,
  getDose,
  getGamification,
  listDoses,
  markOutcome,
  provisionUser,
  psql,
} from "../helpers/api.js";
import { uiLogin } from "../helpers/ui.js";

// Golden path 4 — missed-dose flow: a prior-day unmarked dose is locked by
// the per-minute missed-lock tick → outcome `missed` → −20 points penalty
// (floor-0 clamp) + Horror theme via the ordered replay.

test("unmarked prior-day dose locks as missed and penalizes points", async ({
  page,
}) => {
  const patient = await provisionUser("missed");
  const brand = `E2E-Miss-${Date.now()}`;
  const { medicineId } = await createMedicine(patient.token, patient.userId, {
    brandName: brand,
    dosesRemaining: 30,
    refillThreshold: 6,
  });

  // One schedule, two dose times today (~25 and ~15 min ago, both on-time).
  const t1 = doseSeedMinutesAgo(25);
  const t2 = doseSeedMinutesAgo(15);
  const times = [t1.time, t2.time];
  // Near-midnight fallback can collide on "00:00" — nudge the later slot so
  // scheduledAt ordering (gamification replay) stays deterministic.
  if (times[0] === times[1]) times[1] = "00:01";
  const { scheduleId } = await createSchedule(
    patient.token,
    patient.userId,
    {
      medicineId,
      dates: [t1.date],
      doseTimes: times,
    },
  );
  expect(scheduleId).toBeTruthy();

  const { from, to } = doseWindow();
  const doses = await listDoses(patient.token, patient.userId, from, to);
  expect(doses).toHaveLength(2);
  const byTime = [...doses].sort((a, b) =>
    a.scheduledAt.localeCompare(b.scheduledAt),
  );
  const [earlier, later] = byTime;

  // Mark the EARLIER dose taken (+10); convert the LATER one into a
  // prior-day unmarked dose → missed-lock tick locks it → latest scheduled
  // outcome = missed → theme Horror, points floor-clamped.
  await markOutcome(patient.token, earlier.id, "taken-on-time");
  const yesterday = new Date(Date.now() - 86_400_000)
    .toISOString()
    .slice(0, 10);
  psql(
    "schedule_dose_db",
    `UPDATE dose_occurrences SET local_date='${yesterday}' WHERE id='${later.id}';`,
  );

  // Wait for the per-minute missed-lock tick (≤ ~75s worst case).
  await expect
    .poll(async () => (await getDose(patient.token, later.id)).outcome, {
      timeout: 120_000,
      intervals: [5_000],
    })
    .toBe("missed");

  // Gamification: missed is the latest scheduled outcome → Horror; points
  // = max(0, 10 − 20) = 0.
  await expect
    .poll(
      async () => {
        const g = await getGamification(patient.token, patient.userId);
        return `${g.harmonyPoints}|${g.themeState}`;
      },
      { timeout: 90_000, intervals: [2_000, 5_000] },
    )
    .toBe("0|Horror");

  // UI: Today shows the locked dose as Missed with no actions.
  await uiLogin(page, patient.email);
  const missedCard = page.locator("li[data-dose-id]", {
    has: page.getByTestId("window-badge").filter({ hasText: "Missed" }),
  });
  await expect(missedCard.first()).toBeVisible({ timeout: 30_000 });
  await expect(
    missedCard.first().getByRole("button", { name: "Taken" }),
  ).toHaveCount(0);
});
