import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

async function startWithFallon(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("onboarding")).toBeVisible();
  const fallon = page.getByTestId("preset-fallon_nv");
  const preset = (await fallon.count()) ? fallon : page.locator('[data-testid^="preset-"]').first();
  await preset.click();
  await page.getByTestId("start").click();
  await expect(page.getByTestId("home")).toBeVisible();
}

test("add a second field by drawing it on satellite imagery, then switch between fields", async ({ page }) => {
  await startWithFallon(page);
  await expect(page.getByTestId("field-switcher").first()).toBeVisible();

  await page.getByTestId("field-switcher").first().click();
  await expect(page.getByTestId("fields-sheet")).toBeVisible();
  await page.getByTestId("field-add").click();

  await expect(page.getByTestId("field-editor")).toBeVisible();
  await page.getByTestId("field-name").fill("East pivot");
  const frame = page.frameLocator('[data-testid="map-iframe"]');
  const map = frame.locator("#m.leaflet-container");
  await expect(map).toBeVisible({ timeout: 60_000 });
  await expect(frame.locator(".leaflet-tile-loaded").first()).toBeVisible({ timeout: 60_000 });
  const box = await page.getByTestId("map-iframe").boundingBox();
  if (!box) throw new Error("map not laid out");
  // four corners of a square around the middle of the map
  for (const [dx, dy] of [
    [-60, -60],
    [60, -60],
    [60, 60],
    [-60, 60],
  ]) {
    await map.click({ position: { x: box.width / 2 + dx, y: box.height / 2 + dy } });
    await page.waitForTimeout(300);
  }
  await expect(page.getByTestId("field-area")).toContainText(/4/);
  await page.getByTestId("field-save").click();

  await expect(page.getByTestId("home")).toBeVisible();
  await expect(page.getByTestId("field-switcher").first()).toContainText("East pivot");
  await page.getByTestId("field-switcher").first().click();
  const items = page.locator('[data-testid^="field-item-"]');
  await expect(items).toHaveCount(2);
  await items.first().click();
  await expect(page.getByTestId("field-switcher").first()).not.toContainText("East pivot");
});

test("enable device sync shows a farm code and QR", async ({ page, request }) => {
  const health = await request.post(`${API}/api/farms`, { data: { name: "probe" } }).catch(() => null);
  test.skip(!health || !health.ok(), "farm sync endpoint not available");
  await startWithFallon(page);
  await page.getByTestId("tab-settings").click();
  await page.getByTestId("sync-enable").click();
  await expect(page.getByTestId("sync-code")).toHaveText(/^[A-Z0-9]{4}-[A-Z0-9]{4}$/, { timeout: 30_000 });
  await expect(page.getByTestId("sync-status")).toContainText(/Synced|Syncing/);
});

test("satellite view of a field (Sentinel-2)", async ({ page, request }) => {
  test.setTimeout(600_000);
  const probe = await request.post(`${API}/api/satellite`, { data: { lat: 39.472, lon: -118.777 }, timeout: 60_000 }).catch(() => null);
  test.skip(!probe || probe.status() === 404, "satellite endpoint not available");
  await startWithFallon(page);
  await page.getByTestId("tab-map").click();
  await page.getByTestId("map-view-satellite").click();
  await expect(page.getByTestId("satellite-panel")).toBeVisible();
  await expect(page.getByTestId("ndvi-chart")).toBeVisible({ timeout: 540_000 });
  await expect(page.getByTestId("sat-phenology")).toBeVisible();
});
