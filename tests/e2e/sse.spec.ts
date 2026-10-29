import { test, expect } from "../../web/e2e/test";

test("SSE reconnect after offline converges and remote logout clears private DOM", async ({
  page,
  context,
}) => {
  let creates = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/v2/runs"
    )
      creates++;
  });
  const stream = page.waitForResponse(
    (response) =>
      response.url().endsWith("/events") && response.status() === 200,
  );
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  const response = await stream;
  expect(response.headers()["content-type"]).toContain("text/event-stream");
  expect(new URL(response.url()).search).toBe("");
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeEnabled();
  const id = new URL(page.url()).searchParams.get("run_id")!;
  await context.setOffline(true);
  await page.waitForTimeout(1500);
  await context.setOffline(false);
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeEnabled();
  expect(creates).toBe(1);
  const snapshot = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  expect(snapshot.status).toBe("waiting_for_approval");
  const logout = await page.request.post("/auth/logout");
  expect(logout.status()).toBe(200);
  await expect(
    page.getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(snapshot.request, { exact: true })).toHaveCount(
    0,
  );
});

test("duplicate replay and reset only refresh authoritative state, without repeating a mutation", async ({
  page,
}) => {
  let creates = 0,
    injected = false;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/v2/runs"
    )
      creates++;
  });
  await page.route("**/api/v2/runs/*/events", async (route) => {
    if (injected) {
      await route.continue();
      return;
    }
    injected = true;
    const request = route.request();
    const previous = request.headers()["last-event-id"];
    const body = JSON.parse(
      Buffer.from(previous.split(".")[0], "base64url").toString(),
    );
    const snapshot = await (
      await page.request.get(request.url().replace(/\/events$/, ""))
    ).json();
    const change = `id: ${snapshot.latest_event_id}\nevent: change\ndata: ${JSON.stringify({ sequence: body[5] + 1 })}\n\n`;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: change + change + "event: reset\ndata: {}\n\n",
    });
  });
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeEnabled();
  expect(injected).toBe(true);
  expect(creates).toBe(1);
  const id = new URL(page.url()).searchParams.get("run_id")!;
  const snapshot = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  expect(snapshot.status).toBe("waiting_for_approval");
  expect(snapshot.action.approval_status).toBe("pending");
});
