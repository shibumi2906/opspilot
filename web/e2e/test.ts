import { test as base, expect } from "@playwright/test";
export { expect };
export type { Page } from "@playwright/test";
export const test = base.extend({
  page: async ({ page, baseURL }, use) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Sign in", exact: true }).click();
    await page.locator("#username").fill("demo");
    await page.locator("#password").fill(process.env.OIDC_DEMO_PASSWORD!);
    await page.locator("#kc-login").click();
    await expect(page.getByLabel("Tenant", { exact: true })).toBeVisible();
    await page
      .getByLabel("Tenant", { exact: true })
      .selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    await expect(page.getByTestId("model-mode")).toBeVisible();
    const me = await (await page.request.get("/auth/me")).json();
    await page
      .context()
      .setExtraHTTPHeaders({ "X-CSRF-Token": me.csrf_token, Origin: baseURL! });
    await use(page);
  },
});
