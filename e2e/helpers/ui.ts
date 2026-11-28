// UI helpers — drive the real Next.js app in Chromium.
import { expect, type Page } from "@playwright/test";
import { E2E_PASSWORD } from "./api.js";

export async function uiLogin(
  page: Page,
  email: string,
  password = E2E_PASSWORD,
): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  // Post-login landing races between "/" and "/today" (guest-guard vs
  // LoginScreen next=) — normalize by navigating explicitly.
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });
  await page.goto("/today");
  await expect(page).toHaveURL(/\/today/, { timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "Today", exact: true }),
  ).toBeVisible();
}

export async function uiSignup(
  page: Page,
  input: { name: string; email: string; password?: string; role?: string },
): Promise<void> {
  await page.goto("/signup");
  await page.locator("#name").fill(input.name);
  await page.locator("#email").fill(input.email);
  await page.locator("#password").fill(input.password ?? E2E_PASSWORD);
  if (input.role) {
    await page.locator("#role").selectOption(input.role);
  }
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(
    page.getByRole("heading", { name: "Check your email" }),
  ).toBeVisible();
}
