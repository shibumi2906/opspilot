import { test, expect } from "../../web/e2e/base";
async function signIn(page: any, name: string) {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.locator("#username").fill(name);
  await page.locator("#password").fill(process.env.OIDC_DEMO_PASSWORD!);
  await page.locator("#kc-login").click();
}
test("real OIDC PKCE session, authorized tenant switch, no browser tokens and logout", async ({
  page,
}) => {
  await signIn(page, "demo");
  await page
    .getByLabel("Tenant", { exact: true })
    .selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await expect(page.getByTestId("model-mode")).toBeVisible();
  await expect(page.getByLabel("Tenant", { exact: true })).toHaveValue(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  );
  await expect(page.getByTestId("demo-self-approval")).toBeVisible();
  await page
    .getByLabel("Tenant", { exact: true })
    .selectOption("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
  await expect(page.getByLabel("Tenant", { exact: true })).toHaveValue(
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  );
  const cookies = await page.context().cookies();
  const cookie = cookies.find((c) => c.name === "opspilot_session")!;
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.sameSite).toBe("Lax");
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toMatch(/access_token|refresh_token|id_token|opspilot_session/);
  const raw = cookie.value;
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
  const response = await page.request.get("/auth/me", {
    headers: { Cookie: `opspilot_session=${raw}` },
  });
  expect(response.status()).toBe(401);
});
test("OIDC login never auto-provisions a membership", async ({ page }) => {
  await signIn(page, "unassigned");
  await expect(
    page.getByRole("heading", { name: "No authorized memberships" }),
  ).toBeVisible();
});
