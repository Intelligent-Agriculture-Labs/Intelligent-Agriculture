import { expect, test } from "@playwright/test";
import { API, startWithDemo } from "./helpers";

test("sign up (keeping the local field) → log out → log in again", async ({ page, request }) => {
  test.setTimeout(300_000);
  const probe = await request.get(`${API}/api/auth/me`).catch(() => null);
  test.skip(!probe || probe.status() === 404, "account endpoints not available");
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.org`;
  const password = "correct horse 42";

  await startWithDemo(page);
  await expect(page.getByTestId("account-nudge")).toBeVisible({ timeout: 180_000 }); // shown once the advice is loaded
  await page.getByTestId("account-nudge").click();
  await expect(page.getByTestId("account")).toBeVisible();

  // a friendly validation message before anything is sent
  await page.getByTestId("auth-mode-register").click();
  await page.getByTestId("auth-email").fill("not-an-email");
  await page.getByTestId("auth-password").fill("short");
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("auth-error")).toBeVisible();

  await page.getByTestId("auth-name").fill("E2E Farmer");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(password);
  await expect(page.getByTestId("auth-password")).toHaveAttribute("type", "password");
  await page.getByTestId("auth-password-toggle").click(); // show the password
  await expect(page.getByTestId("auth-password")).not.toHaveAttribute("type", "password");
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("home")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("account-nudge")).toHaveCount(0);

  // the account screen shows the user; log out clears the device
  await page.getByTestId("tab-settings").click();
  await expect(page.getByTestId("row-account")).toContainText(email);
  await page.getByTestId("row-account").click();
  await expect(page.getByTestId("account-profile")).toContainText("E2E Farmer");
  await page.getByTestId("logout").click();
  await expect(page.getByTestId("welcome").or(page.getByTestId("onboarding"))).toBeVisible({ timeout: 30_000 });

  // wrong password → friendly error; right password → the farm comes back from the account
  await page.goto("/account");
  await page.getByTestId("auth-mode-login").click();
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill("wrong password");
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("auth-error")).toContainText(/not correct|incorrect|wrong/i);
  await page.getByTestId("auth-password").fill(password);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("home")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("field-switcher").first()).toContainText(/Fallon|Nevada|field/i);
});
