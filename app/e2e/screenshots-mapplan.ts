// Captures Field (Machakos, Kenya — strong relief), Plan (Fallon, Nevada), multi-year rotation plans
// (Ames, Iowa and Machakos) and the account screen into ../media. Usage:
//   npx serve -s dist -l 4173 & node --experimental-strip-types e2e/screenshots-mapplan.ts
// Fails loudly if the MOCK banner ever appears: screenshots must show real NASA-derived data.
import { chromium, devices, type Page } from "@playwright/test";
import { choose, dismissTips, fullShot, noMock, out, pickCrop, scrollPageTop, scrollToTop } from "./shotlib.ts";

/** Enter history + plan on Plan → Next years and wait for the check. */
async function planYears(page: Page, history: string[], plan: string[]) {
  await page.getByTestId("tab-plan").click();
  await page.getByTestId("plan-tab-years").click();
  await page.getByTestId("rotation-planner").waitFor();
  await dismissTips(page);
  const years = await page
    .locator('[data-testid^="rplan-crop-"]:not([data-testid*="-opt-"])')
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")!));
  for (let i = 0; i < Math.min(years.length, plan.length); i++) await pickCrop(page, years[i], plan[i]);
  await page.getByTestId("rplan-history-toggle").click();
  const hist = await page
    .locator('[data-testid^="rplan-hist-"]:not([data-testid*="-opt-"])')
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")!));
  for (let i = 0; i < Math.min(hist.length, history.length); i++) await pickCrop(page, hist[i], history[i]);
  await page.getByTestId("rplan-history-toggle").click();
  const check = page.getByTestId("rplan-check-main");
  await page.getByTestId("rplan-headline").waitFor({ timeout: 300_000 }); // the first check (default plan) finishes
  // then check the entered plan, if it differs from the default (the button is disabled while a check runs)
  if (await check.isVisible()) await check.click({ timeout: 300_000 });
  await check.waitFor({ state: "hidden", timeout: 300_000 });
  await page.waitForTimeout(1500);
  await noMock(page);
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
  await page.getByTestId("layer-legend-compact").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(9000); // Leaflet tiles + overlay image
  await noMock(page);
  if (label === "desktop") await fullShot(page, `${out}/web-map-${label}.png`);
  else await page.screenshot({ path: `${out}/web-map-${label}.png` });
  await page.getByTestId("layers-button").click();
  await page.getByTestId("layers-sheet").waitFor();
  await page.waitForTimeout(600);
  if (label === "mobile") await page.screenshot({ path: `${out}/web-layers-mobile.png` });
  await page.getByTestId("layer-erosion").click();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(4000);
  if (label === "desktop") await fullShot(page, `${out}/web-map-erosion-${label}.png`);
  else await page.screenshot({ path: `${out}/web-map-erosion-${label}.png` });

  // Machakos: maize after maize → the optimiser proposes a cowpea break (Striga)
  await planYears(page, ["maize", "maize", "maize"], ["maize", "maize", "maize"]);
  await scrollPageTop(page);
  await page.screenshot({ path: `${out}/web-plan-years-machakos-${label}.png` });

  await choose(page, "fallon_nv");
  await page.getByTestId("tab-plan").click();
  await page.getByTestId("plan-timeline").waitFor({ timeout: 180_000 });
  await dismissTips(page);
  await page.getByTestId("plan-water-toggle-toggle").click();
  await page.getByTestId("plan-allocation").fill("1100");
  await page.getByTestId("plan-update").click();
  await page.getByTestId("plan-coverage").waitFor({ timeout: 180_000 });
  await page.waitForTimeout(1500);
  await noMock(page);
  await fullShot(page, `${out}/web-plan-${label}.png`);

  // Ames, Iowa: maize-heavy plan → red years, optimised plan with winter barley + cover crops
  await choose(page, "ames_ia");
  await planYears(page, ["maize", "soybean", "maize"], ["maize", "maize", "soybean", "maize"]);
  await scrollPageTop(page);
  await page.screenshot({ path: `${out}/web-plan-years-check-${label}.png` });
  // the key "impact" view: what the improved plan changes, then the plan to apply
  if (await page.getByTestId("rplan-impact").count()) await scrollToTop(page, "rplan-impact");
  await page.screenshot({ path: `${out}/web-plan-years-${label}.png` });
  await fullShot(page, `${out}/web-plan-years-${label}-full.png`);

  // account screen (a throw-away account on the local server)
  await page.getByTestId("tab-settings").click();
  await page.getByTestId("row-account").click();
  await page.getByTestId("auth-mode-register").click();
  await page.getByTestId("auth-name").fill("Demo Farmer");
  await page.getByTestId("auth-email").fill(`demo-${Date.now()}@example.org`);
  await page.getByTestId("auth-password").fill("field-shift-demo");
  if (label === "mobile") await page.screenshot({ path: `${out}/web-signup-mobile.png` });
  await page.getByTestId("auth-submit").click();
  await page.getByTestId("home").waitFor({ timeout: 60_000 });
  await page.getByTestId("tab-settings").click();
  await page.getByTestId("row-account").click();
  await page.getByTestId("account-profile").waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/web-account-${label}.png` });
  await ctx.close();
}
await browser.close();
console.log("map/plan/account screenshots written to", out);
