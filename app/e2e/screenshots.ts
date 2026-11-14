// Captures README screenshots of the web app into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots.ts
import { chromium, devices } from "@playwright/test";
import { base, choose, dismissTips, fullShot, noMock, out } from "./shotlib.ts";

const browser = await chromium.launch();
for (const [label, ctxOpts] of [
  ["mobile", { ...devices["Pixel 7"] }],
  ["desktop", { viewport: { width: 1280, height: 900 } }],
] as const) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  // first run: welcome tour, then the demo farms
  await page.goto(base);
  await page.getByTestId("welcome").waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/web-welcome-${label}.png` });
  await page.getByTestId("welcome-skip").click();
  await page.getByTestId("onboarding").waitFor();
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/web-onboarding-${label}.png` });

  await choose(page, "fallon_nv");
  await page.getByTestId("action-card-0").waitFor({ timeout: 180_000 });
  await dismissTips(page);
  await page.waitForTimeout(800);
  await noMock(page);
  if (label === "mobile") await page.screenshot({ path: `${out}/web-home.png` });
  else await fullShot(page, `${out}/web-home-desktop.png`);
  if (label === "mobile") {
    await page.getByTestId("share-text").click();
    await page.getByTestId("share-text-preview").waitFor({ timeout: 60_000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${out}/web-share-text-mobile.png` });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
  }
  await page.getByTestId("action-card-0").click();
  await page.getByTestId("why").waitFor();
  await page.waitForTimeout(800);
  await fullShot(page, `${out}/web-why-${label}.png`);
  await page.goBack();

  await page.getByTestId("tab-insights").click();
  await page.getByTestId("insights").waitFor();
  await dismissTips(page);
  await page.waitForTimeout(500);
  await fullShot(page, `${out}/web-insights-${label}.png`);
  for (const tab of ["rotations", "whatif", "climate"]) {
    await page.getByTestId("tab-insights").click();
    await page.getByTestId(`insights-${tab}`).click();
    await page.getByTestId(tab).waitFor();
    // wait for content beyond the loading spinner (max 3 min for cold NASA fetches)
    const ready = tab === "rotations" ? "strategy-0" : tab === "whatif" ? "stat-yield" : null;
    if (ready) await page.getByTestId(ready).waitFor({ timeout: 180_000 });
    else await page.waitForTimeout(6000);
    await page.waitForTimeout(800);
    await noMock(page);
    await fullShot(page, `${out}/web-${tab}-${label}.png`);
  }
  await ctx.close();
}
await browser.close();
console.log("screenshots written to", out);
