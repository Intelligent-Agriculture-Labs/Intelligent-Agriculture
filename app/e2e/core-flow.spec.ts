import { expect, test } from "@playwright/test";

test("core flow: pick demo farm → 3 action cards → Why? with chart", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("onboarding")).toBeVisible();

  // hero demo farm (Fallon, Nevada); fall back to the first preset if ids change
  const fallon = page.getByTestId("preset-fallon_nv");
  const preset = (await fallon.count()) ? fallon : page.locator('[data-testid^="preset-"]').first();
  await preset.click();
  await page.getByTestId("start").click();

  await expect(page.getByTestId("home")).toBeVisible();
  // home shows the top (max 3) prioritized action cards
  await expect(page.getByTestId("action-card-0")).toBeVisible();
  const cards = await page.locator('[data-testid^="action-card-"]').count();
  expect(cards).toBeGreaterThanOrEqual(1);
  expect(cards).toBeLessThanOrEqual(3);
  await expect(page.getByTestId("attribution")).toContainText(/NASA/i);

  await page.getByTestId("action-card-0").click();
  await expect(page.getByTestId("why")).toBeVisible();
  await expect(page.locator('[data-testid^="chart-"]').first()).toBeVisible();
  await expect(page.getByTestId("confidence")).toBeVisible();
});

test("rotations tab compares at least three strategies", async ({ page }) => {
  await page.goto("/");
  const preset = page.locator('[data-testid^="preset-"]').first();
  await preset.click();
  await page.getByTestId("start").click();
  await page.getByTestId("tab-rotations").click();
  await expect(page.getByTestId("strategy-2")).toBeVisible();
});
