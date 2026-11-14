// Shared helpers for the screenshot scripts (not a test file).
import type { Page } from "@playwright/test";

export const base = process.env.E2E_BASE_URL ?? "http://localhost:4173";
export const out = process.env.SHOT_DIR ?? "../media";

/** Fresh device → skip the welcome tour → open a demo farm. */
export async function choose(page: Page, preset: string) {
  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.goto(base);
  await page.getByTestId("welcome-skip").click();
  await page.getByTestId("onboarding").waitFor();
  await page.getByTestId(`preset-${preset}`).click();
  await page.waitForTimeout(800);
  await page.getByTestId("start").click();
  await page.getByTestId("home").waitFor();
}

/** Screenshots must show real NASA-derived data. */
export async function noMock(page: Page) {
  if (await page.getByTestId("mock-banner").count()) throw new Error("MOCK banner visible — refusing to capture");
}

/** Close the one-time tips so marketing shots show the content. */
export async function dismissTips(page: Page) {
  // tips on inactive tabs are inert (not clickable) — only close the ones on screen
  for (const b of await page.locator('[aria-label="Got it"]:not([inert] *)').all()) await b.click({ timeout: 3000 }).catch(() => undefined);
}

/** Pick a crop in a CropPicker (sheet with options `${testID}-opt-${crop}`). */
export async function pickCrop(page: Page, testID: string, crop: string) {
  await page.getByTestId(testID).click();
  await page.getByTestId(`${testID}-opt-${crop}`).click();
  await page.waitForTimeout(300);
}

/** Scroll the (React Native Web inner) scroll view so that `testID` sits at the top of the screen. */
export async function scrollToTop(page: Page, testID: string) {
  await page.getByTestId(testID).evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(400);
}

/**
 * Full-length capture: RN Web scrolls inside a view, so Playwright's fullPage sees only the window.
 * Temporarily grow the viewport to the content height instead.
 */
export async function fullShot(page: Page, path: string) {
  const vp = page.viewportSize()!;
  const h = await page.evaluate(() => Math.max(...Array.from(document.querySelectorAll("*")).map((e) => (e as HTMLElement).scrollHeight)));
  await page.setViewportSize({ width: vp.width, height: Math.min(Math.max(h + 120, vp.height), 7000) });
  await page.waitForTimeout(800);
  await page.screenshot({ path });
  await page.setViewportSize(vp);
  await page.waitForTimeout(300);
}

/** Scroll every scrolled container back to the top (RN Web scroll views are plain divs). */
export async function scrollPageTop(page: Page) {
  await page.evaluate(() => document.querySelectorAll("*").forEach((e) => ((e as HTMLElement).scrollTop = 0)));
  await page.waitForTimeout(400);
}
