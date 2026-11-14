// Captures marketing/README screenshots of the web app into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots.ts
import { chromium, devices } from "@playwright/test";

const base = process.env.E2E_BASE_URL ?? "http://localhost:4173";
const out = process.env.SHOT_DIR ?? "../media";

const browser = await chromium.launch();
for (const [label, ctxOpts] of [
  ["mobile", { ...devices["Pixel 7"] }],
  ["desktop", { viewport: { width: 1280, height: 900 } }],
] as const) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  await page.goto(base);
  await page.getByTestId("onboarding").waitFor();
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/web-onboarding-${label}.png` });
  await page.getByTestId("preset-fallon_nv").click();
  await page.waitForTimeout(1500);
  await page.getByTestId("start").click();
  await page.getByTestId("action-card-0").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: label === "mobile" ? `${out}/web-home.png` : `${out}/web-home-desktop.png`, fullPage: label === "desktop" });
  await page.getByTestId("action-card-0").click();
  await page.getByTestId("why").waitFor();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/web-why-${label}.png`, fullPage: true });
  await page.goBack();
  for (const tab of ["rotations", "whatif", "climate"]) {
    await page.getByTestId(`tab-${tab}`).click();
    await page.getByTestId(tab).waitFor();
    await page.waitForTimeout(tab === "rotations" ? 1000 : 500);
    // wait for content beyond loading spinner (max 3 min for cold NASA fetches)
    const ready = tab === "rotations" ? "strategy-0" : tab === "whatif" ? "stat-yield" : null;
    if (ready) await page.getByTestId(ready).waitFor({ timeout: 180_000 });
    else await page.waitForTimeout(6000);
    await page.screenshot({ path: `${out}/web-${tab}-${label}.png`, fullPage: true });
  }
  await ctx.close();
}
await browser.close();
console.log("screenshots written to", out);
