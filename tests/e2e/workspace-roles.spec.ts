import { test, expect } from "../../web/e2e/base";
async function login(page: any, name: string) {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.locator("#username").fill(name);
  await page.locator("#password").fill(process.env.OIDC_DEMO_PASSWORD!);
  await page.locator("#kc-login").click();
  await page
    .getByLabel("Tenant", { exact: true })
    .selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await expect(page.getByTestId("model-mode")).toBeVisible();
}
test("admin controls and auditor view are separated; mobile keyboard navigation", async ({
  browser,
  baseURL,
}) => {
  const admin = await browser.newContext({ baseURL });
  const page = await admin.newPage();
  await login(page, "admin");
  await expect(
    page.getByRole("button", { name: "History", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Administration", exact: true })
    .click();
  const region = page.getByRole("region", { name: "Tenant administration" });
  await expect(region).toBeVisible();
  const connection = region.locator(".workspace-list > li").first();
  await connection
    .getByRole("button", { name: "Disable connection", exact: true })
    .click();
  await expect(
    connection.getByRole("button", { name: "Enable connection", exact: true }),
  ).toBeVisible();
  await connection
    .getByRole("button", { name: "Enable connection", exact: true })
    .click();
  await expect(
    connection.getByRole("button", { name: "Disable connection", exact: true }),
  ).toBeVisible();
  await admin.close();
  const auditor = await browser.newContext({
    baseURL,
    viewport: { width: 390, height: 844 },
  });
  const ap = await auditor.newPage();
  await login(ap, "auditor");
  await expect(
    ap.getByRole("button", { name: "Administration", exact: true }),
  ).toHaveCount(0);
  await ap.getByRole("button", { name: "Audit", exact: true }).click();
  await expect(ap.getByRole("heading", { name: "Tenant audit" })).toBeFocused();
  await expect(ap.getByRole("region", { name: "Tenant audit" })).toContainText(
    "connector_config_changed",
  );
  const download = ap.waitForEvent("download");
  await ap.getByRole("button", { name: "Download audit page" }).click();
  await download;
  expect(
    await ap.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  await ap.keyboard.press("Tab");
  expect(await ap.evaluate(() => document.activeElement?.tagName)).toBe(
    "BUTTON",
  );
  await auditor.close();
});
