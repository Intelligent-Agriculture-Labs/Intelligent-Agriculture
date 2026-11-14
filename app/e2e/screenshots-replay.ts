// Captures the "replay a summer week" demo state (Fallon, 15 Jul 2025) on web into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots-replay.ts
import { chromium, devices } from "@playwright/test";
import { choose, dismissTips, out } from "./shotlib.ts";

const browser = await chromium.launch();
for (const [label, ctxOpts] of [
  ["mobile", { ...devices["Pixel 7"] }],
  ["desktop", { viewport: { width: 1280, height: 900 } }],
] as const) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  await choose(page, "fallon_nv");
  await page.getByTestId("mode-replay").click({ timeout: 180_000 });
  await page
    .getByText(/Irrigate/)
    .first()
    .waitFor({ timeout: 240_000 });
  await dismissTips(page);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/web-replay-home-${label}.png`, fullPage: label === "desktop" });
  await page.getByTestId("action-card-0").click();
  await page.getByTestId("why").waitFor();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/web-replay-why-${label}.png`, fullPage: true });
  await ctx.close();
}
await browser.close();
console.log("replay screenshots written to", out);
