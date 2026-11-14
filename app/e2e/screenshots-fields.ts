// Captures the multi-field / sync / satellite screenshots into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots-fields.ts [--satellite]
// Uses the real demo-farm fields from /api/presets (Fallon alfalfa field with its outline).
// Fails loudly if the MOCK banner ever appears: screenshots must show real data.
import { chromium, devices, type Page } from "@playwright/test";
import { choose, noMock, out } from "./shotlib.ts";

const withSatellite = process.argv.includes("--satellite");

async function detectAtCenter(page: Page) {
  const frame = page.frameLocator('[data-testid="map-iframe"]');
  const map = frame.locator("#m.leaflet-container");
  await map.waitFor({ timeout: 60_000 });
  await frame.locator(".leaflet-tile-loaded").first().waitFor({ timeout: 60_000 });
  const box = await page.getByTestId("map-iframe").boundingBox();
  if (!box) throw new Error("map not laid out");
  await map.click({ position: { x: box.width / 2 + 25, y: box.height / 2 + 15 } }); // inside the field, off the pin
  await page.getByTestId("detect-result").waitFor({ timeout: 90_000 });
  await page.waitForTimeout(5000); // fit-to-field + high-res tiles
}

const browser = await chromium.launch();

// 1) desktop: automatic boundary detection on the Fallon alfalfa field, then the field list
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1100 } });
  const page = await ctx.newPage();
  await choose(page, "fallon_nv");
  await noMock(page);
  await page.getByTestId("field-switcher").first().click();
  await page.getByTestId("field-add").click();
  await page.getByTestId("field-editor").waitFor();
  await page.getByTestId("field-name").fill("Alfalfa — north pivot");
  await detectAtCenter(page);
  await page.getByTestId("editor-map").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${out}/web-fields-desktop.png` });
  await page.getByTestId("field-save").click();
  await page.getByTestId("home").waitFor();
  await page.waitForTimeout(1500);
  await page.getByTestId("field-switcher").first().click();
  await page.getByTestId("fields-sheet").waitFor();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/web-fields-list-desktop.png` });
  await ctx.close();
}

// 1b) mobile: tap-to-detect result with confidence badge
{
  const ctx = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await ctx.newPage();
  await choose(page, "fallon_nv");
  await page.getByTestId("field-switcher").first().click();
  await page.getByTestId("field-add").click();
  await page.getByTestId("field-editor").waitFor();
  await detectAtCenter(page);
  await page.getByTestId("editor-map").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -60));
  await page.screenshot({ path: `${out}/web-detect-mobile.png` });
  await ctx.close();
}

// 2) mobile: device sync code + QR
{
  const ctx = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await ctx.newPage();
  await choose(page, "fallon_nv");
  await page.getByTestId("tab-settings").click();
  await page.getByTestId("row-share").click();
  await page.getByTestId("sync-enable").click();
  await page.getByTestId("sync-code").waitFor({ timeout: 30_000 });
  await page.waitForTimeout(2500);
  await page.getByTestId("sync-card").scrollIntoViewIfNeeded();
  await noMock(page);
  await page.getByTestId("sync-card").screenshot({ path: `${out}/web-sync-mobile.png` });
  await ctx.close();
}

// 3) satellite view (needs /api/satellite); the field outline comes from the preset or is drawn here
if (withSatellite) {
  for (const [label, ctxOpts] of [
    ["desktop", { viewport: { width: 1280, height: 1000 } }],
    ["mobile", { ...devices["Pixel 7"] }],
  ] as const) {
    const ctx = await browser.newContext(ctxOpts);
    const page = await ctx.newPage();
    await choose(page, "fallon_nv");
    await page.getByTestId("tab-map").click();
    await page.getByTestId("map-view-satellite").click();
    await page.getByTestId("ndvi-chart").waitFor({ timeout: 900_000 });
    await page.waitForTimeout(8000);
    await noMock(page);
    await page.screenshot({ path: `${out}/web-satellite-${label}.png`, fullPage: true });
    await ctx.close();
  }
}

await browser.close();
console.log("field/sync screenshots written to", out);
