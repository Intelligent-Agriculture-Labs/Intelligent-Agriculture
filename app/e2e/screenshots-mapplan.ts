// Captures Map (Machakos, Kenya — strong relief) and Plan (Fallon, Nevada) screenshots into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots-mapplan.ts
// Fails loudly if the MOCK banner ever appears: screenshots must show real NASA-derived data.
import { chromium, devices, type Page } from "@playwright/test";

const base = process.env.E2E_BASE_URL ?? "http://localhost:4173";
const out = process.env.SHOT_DIR ?? "../media";

async function choose(page: Page, preset: string) {
  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.goto(base);
  await page.getByTestId("onboarding").waitFor();
  await page.getByTestId(`preset-${preset}`).click();
  await page.waitForTimeout(800);
  await page.getByTestId("start").click();
  await page.getByTestId("home").waitFor();
}

async function noMock(page: Page) {
  if (await page.getByTestId("mock-banner").count()) throw new Error("MOCK banner visible — refusing to capture");
}

const browser = await chromium.launch();
for (const [label, ctxOpts] of [
  ["mobile", { ...devices["Pixel 7"] }],
  ["desktop", { viewport: { width: 1280, height: 900 } }],
] as const) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  await choose(page, "machakos_ke");
  await page.getByTestId("tab-map").click();
  await page.getByTestId("layer-legend").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(9000); // Leaflet tiles + overlay image
  await noMock(page);
  await page.screenshot({ path: `${out}/web-map-${label}.png`, fullPage: label === "desktop" });
  await page.getByTestId("layer-erosion").click();
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${out}/web-map-erosion-${label}.png`, fullPage: label === "desktop" });

  await choose(page, "fallon_nv");
  await page.getByTestId("tab-plan").click();
  await page.getByTestId("plan-timeline").waitFor({ timeout: 180_000 });
  await page.getByTestId("plan-allocation").fill("1100");
  await page.getByTestId("plan-update").click();
  await page.getByTestId("plan-coverage").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(1500);
  await noMock(page);
  await page.screenshot({ path: `${out}/web-plan-${label}.png`, fullPage: true });
  await ctx.close();
}
await browser.close();
console.log("map/plan screenshots written to", out);
