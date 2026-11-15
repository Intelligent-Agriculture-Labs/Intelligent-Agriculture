import { expect, test } from "@playwright/test";
import { API, startWithDemo } from "./helpers";

test("core flow: demo farm → at most 3 action cards → Why? with chart", async ({ page }) => {
  test.setTimeout(300_000);
  await startWithDemo(page);
  await expect(page.getByTestId("action-card-0")).toBeVisible({ timeout: 180_000 });
  const cards = await page.locator('[data-testid^="action-card-"]').count();
  expect(cards).toBeGreaterThanOrEqual(1);
  expect(cards).toBeLessThanOrEqual(3);
  await expect(page.getByTestId("attribution")).toContainText(/NASA/i);

  // this week's advice as a short text message (SMS / WhatsApp)
  await page.getByTestId("share-text").click();
  await expect(page.getByTestId("share-text-preview")).toContainText(/^IA/, { timeout: 60_000 });
  await expect(page.getByTestId("share-text-sms")).toContainText(/SMS/);
  await page.keyboard.press("Escape");

  // everything else lives behind "More about your field this week"
  await page.getByTestId("more-week-toggle").click();
  await expect(page.getByTestId("drought-chip")).toBeVisible();

  await page.getByTestId("action-card-0").click();
  await expect(page.getByTestId("why")).toBeVisible();
  await expect(page.locator('[data-testid^="chart-"]').first()).toBeVisible();
  await expect(page.getByTestId("confidence")).toBeVisible();
});

test("first run: welcome tour → tap inside the field → detected outline → Today", async ({ page, request }) => {
  const probe = await request.post(`${API}/api/fields/detect`, { data: { lat: 39.44087, lon: -118.83012 }, timeout: 60_000 }).catch(() => null);
  test.skip(!probe || !probe.ok(), "field detection endpoint not available");
  await page.goto("/");
  await expect(page.getByTestId("welcome")).toBeVisible();
  await expect(page.getByTestId("welcome-title-0")).toBeVisible();
  await page.getByTestId("welcome-next").click();
  await expect(page.getByTestId("welcome-title-1")).toBeVisible();
  await page.getByTestId("welcome-next").click();
  await expect(page.getByTestId("welcome-title-2")).toBeVisible();
  await page.getByTestId("welcome-add").click();

  await expect(page.getByTestId("field-editor")).toBeVisible();
  await page.getByTestId("field-name").fill("Home field");
  // move the map to a centre-pivot field near Fallon, Nevada by typing its coordinates
  await page.getByTestId("field-coords").fill("39.44087, -118.83012");
  await page.getByTestId("field-coords-go").click();
  const frame = page.frameLocator('[data-testid="map-iframe"]');
  const map = frame.locator("#m.leaflet-container");
  await expect(map).toBeVisible({ timeout: 60_000 });
  await expect(frame.locator(".leaflet-tile-loaded").first()).toBeVisible({ timeout: 60_000 });
  const box = await page.getByTestId("map-iframe").boundingBox();
  if (!box) throw new Error("map not laid out");
  await map.click({ position: { x: box.width / 2 + 25, y: box.height / 2 + 15 } });
  await expect(page.getByTestId("detect-result")).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("field-save").click();
  await expect(page.getByTestId("home")).toBeVisible();
  await expect(page.getByTestId("field-switcher").first()).toContainText("Home field");
});

test("Insights → rotation strategies compares at least three strategies", async ({ page }) => {
  await startWithDemo(page);
  await page.getByTestId("tab-insights").click();
  await page.getByTestId("insights-rotations").click();
  await expect(page.getByTestId("strategy-2")).toBeVisible({ timeout: 120_000 });
  await page.getByTestId("back-insights").click();
  await expect(page.getByTestId("insights-whatif")).toBeVisible();
});

test("Field tab: terrain zones with a layers sheet; Plan tab: season plan", async ({ page }) => {
  await startWithDemo(page);
  await page.getByTestId("tab-map").click();
  await expect(page.getByTestId("map-screen")).toBeVisible();
  await expect(page.getByTestId("layer-legend-compact")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("terrain-map-iframe")).toBeVisible();
  await page.getByTestId("layers-button").click();
  await page.getByTestId("layer-erosion").click();
  await page.keyboard.press("Escape");
  await page.getByTestId("map-legend-toggle").click();
  await expect(page.getByTestId("layer-legend")).toContainText(/t\/ha|Erosion/i);

  await page.getByTestId("tab-plan").click();
  await expect(page.getByTestId("plan-screen")).toBeVisible();
  await expect(page.getByTestId("plan-timeline")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("op-0")).toBeVisible();
  await page.getByTestId("plan-water-toggle-toggle").click();
  await expect(page.getByTestId("plan-water")).toBeVisible();
});

test("Plan → next years: check the rotation, then apply an improvement", async ({ page, request }) => {
  test.setTimeout(420_000);
  const probe = await request
    .post(`${API}/api/rotations/plan`, {
      data: {
        lat: 39.44,
        lon: -118.84,
        irrigation: "pivot",
        history: [],
        plan: [
          { year: 2027, crop: "maize", cover_crop: null },
          { year: 2028, crop: "maize", cover_crop: null },
        ],
        lang: "en",
        optimize: false,
      },
      timeout: 180_000,
    })
    .catch(() => null);
  test.skip(!probe || !probe.ok(), "rotation plan endpoint not available");
  await startWithDemo(page);
  await page.getByTestId("tab-plan").click();
  await page.getByTestId("plan-tab-years").click();
  await expect(page.getByTestId("rotation-planner")).toBeVisible();
  const headline = page.getByTestId("rplan-headline");
  await expect(headline).toBeVisible({ timeout: 240_000 });
  await expect(page.locator('[data-testid^="rplan-year-"]').first()).toBeVisible();

  // edit: grow maize in the first plan year → the result is stale → check again
  const firstCrop = page.locator('[data-testid^="rplan-crop-"]').first();
  const id = await firstCrop.getAttribute("data-testid");
  await firstCrop.click();
  await page.getByTestId(`${id}-opt-maize`).click();
  await expect(page.getByTestId("rplan-check-main")).toBeVisible();
  await page.getByTestId("rplan-check-main").click();
  await expect(page.getByTestId("rplan-check-main")).toBeHidden({ timeout: 240_000 });
  await expect(headline).toBeVisible();

  if (await page.getByTestId("rplan-impact").count()) {
    await expect(page.locator('[data-testid^="impact-"]').first()).toBeVisible();
    await page.getByTestId("rplan-impact-method-toggle").click();
  }
  const apply = page.getByTestId("rplan-optimized-apply").or(page.getByTestId("rplan-suggestion-0-apply")).first();
  if (await apply.count()) {
    const before = await headline.innerText();
    await apply.click();
    await expect(headline).not.toHaveText(before, { timeout: 240_000 });
  }
});
