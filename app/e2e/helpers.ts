import { expect, type Page } from "@playwright/test";

export const API = process.env.E2E_API_URL ?? "http://localhost:8000";

/** First run: the welcome tour appears; "Skip" leads to the demo farms. */
export async function skipWelcome(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("welcome").or(page.getByTestId("onboarding"))).toBeVisible();
  if (await page.getByTestId("welcome").isVisible()) await page.getByTestId("welcome-skip").click();
  await expect(page.getByTestId("onboarding")).toBeVisible();
}

/** Skip the welcome tour and open a demo farm (Fallon, Nevada by default). */
export async function startWithDemo(page: Page, preset = "fallon_nv") {
  await skipWelcome(page);
  const wanted = page.getByTestId(`preset-${preset}`);
  const card = (await wanted.count()) ? wanted : page.locator('[data-testid^="preset-"]').first();
  await card.click();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("home")).toBeVisible();
}
