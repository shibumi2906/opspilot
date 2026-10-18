import { test, expect, type Page } from "../../web/e2e/test";
import { ticketCount } from "../../web/e2e/database";
import type { RunSnapshot } from "../../web/src/api/types";
async function start(
  page: Page,
  request = "Investigate why GreenShop orders fail today",
) {
  await page.goto("/");
  await expect(page.getByTestId("model-mode")).toHaveText("Scripted model");
  await page.getByLabel("What needs attention?").fill(request);
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page).toHaveURL(/run_id=[0-9a-f-]+/);
}
async function pending(page: Page) {
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeEnabled();
  const id = new URL(page.url()).searchParams.get("run_id")!;
  const response = await page.request.get(`/api/v1/runs/${id}`);
  return (await response.json()) as RunSnapshot;
}
async function snapshot(page: Page) {
  return (await (
    await page.request.get(
      `/api/v1/runs/${new URL(page.url()).searchParams.get("run_id")}`,
    )
  ).json()) as RunSnapshot;
}

test("GreenShop: live trail, evidence, immutable refresh, double click and verified ticket", async ({
  page,
}) => {
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v1/runs"))
      posts++;
  });
  await start(page);
  const saved = await pending(page);
  expect(saved.timeline.some((step) => step.type === "ai")).toBeTruthy();
  expect(saved.timeline.some((step) => step.type === "core")).toBeTruthy();
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
  await page.locator(".source-button").first().click();
  await expect(
    page.getByRole("article", { name: "Evidence detail" }),
  ).toBeVisible();
  await expect(page.locator("#evidence-detail")).toContainText(
    "Asia/Jerusalem",
  );
  await page.reload();
  await pending(page);
  expect(posts).toBe(1);
  const reloaded = await snapshot(page);
  expect(reloaded.action).toEqual(saved.action);
  await expect(page.getByTestId("ticket-title")).toHaveText(
    saved.action!.arguments.title,
  );
  await expect(page.getByTestId("ticket-description")).toHaveText(
    saved.action!.arguments.description,
  );
  // Two same-task clicks exercise the synchronous mutation guard, before a React rerender.
  await page
    .getByRole("button", { name: "Approve & create ticket", exact: true })
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  await expect(
    page.getByRole("heading", { name: "Ticket verified." }),
  ).toBeVisible();
  await expect(page.getByTestId("verification-status")).toHaveText("verified");
  const result = await snapshot(page);
  expect(result.outcome).toBe("actions_verified");
  expect(await ticketCount(saved.action!.action_id)).toBe(1);
  const repeat = await page.request.post(
    `/api/v1/runs/${saved.run_id}/decision`,
    { data: { action_id: saved.action!.action_id, decision: "approve" } },
  );
  expect(repeat.status()).toBe(200);
  expect((await repeat.json()).ticket_id).toBe(result.report!.ticket_id);
  await page.reload();
  await expect(page.getByTestId("created-ticket-id")).toHaveText(
    result.report!.ticket_id!,
  );
  expect(await ticketCount(saved.action!.action_id)).toBe(1);
});

test("Reject creates no ticket and keeps the card visible", async ({
  page,
}) => {
  const before = await ticketCount();
  await start(page);
  const saved = await pending(page);
  await page
    .getByRole("button", { name: "Reject action", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Decision respected." }),
  ).toBeVisible();
  await expect(page.getByTestId("approval-status")).toHaveText("rejected");
  expect(await ticketCount()).toBe(before);
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
  await expect(page.getByTestId("ticket-description")).toHaveText(
    saved.action!.arguments.description,
  );
});

test("polling reconnects without overlapping reads or losing the URL", async ({
  page,
}) => {
  await start(page);
  await pending(page);
  const url = page.url();
  let attempts = 0,
    active = 0,
    maxActive = 0;
  await page.route("**/api/v1/runs/*", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    active++;
    maxActive = Math.max(maxActive, active);
    attempts++;
    await new Promise((resolve) => setTimeout(resolve, 1100));
    active--;
    if (attempts < 3) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Snapshot unavailable");
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeEnabled({ timeout: 25000 });
  expect(page.url()).toBe(url);
  expect(maxActive).toBe(1);
  expect(attempts).toBeGreaterThanOrEqual(3);
  await page.unroute("**/api/v1/runs/*");
  await page
    .getByRole("button", { name: "Reject action", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Decision respected." }),
  ).toBeVisible();
});

test("lost decision response reconciles the server decision before retry", async ({
  page,
}) => {
  await start(page);
  const saved = await pending(page);
  let decisions = 0;
  await page.route("**/decision", async (route) => {
    decisions++;
    await route.fetch();
    await route.abort("connectionfailed");
  });
  await page
    .getByRole("button", { name: "Approve & create ticket", exact: true })
    .click();
  await expect(page.getByTestId("approval-status")).toHaveText("approved");
  await expect(page.getByTestId("verification-status")).toHaveText("verified");
  expect(decisions).toBe(1);
  expect(await ticketCount(saved.action!.action_id)).toBe(1);
});

test("narrow viewport, plain text sources and readable partial results", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page);
  const saved = await pending(page);
  const text = '<img src=x onerror="window.injected=true"> ignore policy';
  await page.route("**/api/v1/runs/*", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const value = (await response.json()) as RunSnapshot;
    value.evidence[0].excerpt = text;
    await route.fulfill({ response, json: value });
  });
  await page.reload();
  await expect(page.locator(".source-button").first()).toBeVisible();
  await page.locator(".source-button").first().click();
  await expect(page.locator("#evidence-detail")).toContainText(text);
  expect(await page.locator("#evidence-detail img").count()).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.unroute("**/api/v1/runs/*");
  await page
    .getByRole("button", { name: "Reject action", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Decision respected." }),
  ).toBeVisible();
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
});

test("status-only completes without an approval card; terminal polling stops", async ({
  page,
}) => {
  await start(page, "Check BlueMarket status");
  await expect(
    page.getByRole("region", { name: "Final report" }),
  ).toBeVisible();
  expect(await page.getByTestId("approval-card").count()).toBe(0);
  const result = await snapshot(page);
  expect(result.outcome).toBe("diagnosis_only");
  let polls = 0;
  page.on("request", (request) => {
    if (request.method() === "GET" && /\/runs\//.test(request.url())) polls++;
  });
  await page.waitForTimeout(2400);
  expect(polls).toBe(0);
});

test("missing run and failed/unknown snapshots never display verified success", async ({
  page,
}) => {
  await page.goto("/?run_id=ffffffff-ffff-ffff-ffff-ffffffffffff");
  await expect(page.getByRole("alert")).toContainText("could not be found");
  await page
    .getByRole("button", { name: "Start a new investigation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Start investigation", exact: true }),
  ).toBeEnabled();
  await start(page);
  const saved = await pending(page);
  await page.route("**/api/v1/runs/*", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const value = (await response.json()) as RunSnapshot;
    value.status = "failed";
    value.error = { code: "RUN_FAILED" };
    value.report = null;
    await route.fulfill({ response, json: value });
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Execution needs review." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeDisabled();
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
});

test("a lost create response reuses the client request ID", async ({
  page,
}) => {
  const keys: string[] = [];
  const ids: string[] = [];
  await page.route("**/api/v1/runs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().postDataJSON().client_request_id);
    const response = await route.fetch();
    ids.push((await response.json()).run_id);
    if (keys.length === 1) await route.abort("connectionfailed");
    else await route.fulfill({ response });
  });
  await page.goto("/");
  await expect(page.getByTestId("model-mode")).toHaveText("Scripted model");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  const saved = await pending(page);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(ids[0]).toBe(ids[1]);
  expect(saved.run_id).toBe(ids[0]);
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
  await page
    .getByRole("button", { name: "Reject action", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Decision respected." }),
  ).toBeVisible();
});

test("unknown and partial projections stay visibly unverified; snapshot mode is authoritative", async ({
  page,
}) => {
  await start(page);
  const saved = await pending(page);
  await page.route("**/api/v1/runs/*", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const value = (await response.json()) as RunSnapshot;
    value.status = "completed";
    value.outcome = "unknown_outcome";
    value.mode = "real";
    value.action!.execution_status = "unknown";
    value.action!.approval_status = "approved";
    value.report = {
      summary: "Write outcome is unknown.",
      facts: [],
      hypotheses: [],
      missing_checks: ["get_ticket"],
      action_summary: "Ticket creation outcome is unknown.",
      ticket_id: null,
      verification_status: "unknown",
      remaining_problem: "Order recovery is unconfirmed.",
      outcome: "unknown_outcome",
    };
    await route.fulfill({ response, json: value });
  });
  await page.reload();
  await expect(page.getByTestId("model-mode")).toHaveText("Real model");
  await expect(page.getByTestId("verification-status")).toHaveText("unknown");
  await expect(
    page.getByRole("region", { name: "Final report" }),
  ).toContainText("Ticket creation outcome is unknown");
  expect(
    await page.getByRole("heading", { name: "Ticket verified." }).count(),
  ).toBe(0);
  expect(await ticketCount(saved.action!.action_id)).toBe(0);
});
