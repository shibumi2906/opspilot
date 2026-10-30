import { test, expect } from "../../web/e2e/test";

test("workspace clarification, cancellation, history and scoped download", async ({
  page,
}) => {
  await page.getByLabel("What needs attention?").fill("Investigate Green");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  const choice = page.getByLabel("Choose customer");
  await expect(choice).toBeVisible();
  await choice.selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "Submit clarification", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Cancel investigation", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Cancel investigation", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Investigation controls" }),
  ).toContainText("cancelled");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download investigation metadata" })
    .click();
  expect((await download).suggestedFilename()).toBe("opspilot-export.json");
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Investigation history" }),
  ).toBeFocused();
  await page
    .getByRole("button", { name: "Investigate Green", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("region", { name: "Investigation controls" }),
  ).toContainText("cancelled");
});

test("workspace revision and private notification render hostile text safely", async ({
  page,
}) => {
  await page
    .getByLabel("What needs attention?")
    .fill("Investigate GreenShop and notify manager");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  const inbox = page.locator('[data-action-key="inbox"]');
  await expect(inbox).toBeVisible();
  const me = await (await page.request.get("/auth/me")).json();
  const edit = page.getByRole("region", { name: "Revision controls inbox" });
  await edit.getByRole("button", { name: "Edit proposed revision" }).click();
  const body = "<img src=x onerror=alert(1)> F14 private notification";
  await edit.getByLabel("Revision body").fill(body);
  await edit.getByLabel("Revision recipient ID").fill(me.user_id);
  await edit.getByRole("button", { name: "Save new revision" }).click();
  await expect(inbox).toContainText(body);
  await page
    .locator('[data-action-key="ticket"]')
    .getByRole("button", { name: "Reject action", exact: true })
    .click();
  await inbox
    .getByRole("button", { name: "Approve & notify recipient", exact: true })
    .click();
  await expect(page.getByTestId("plan-node-inbox")).toContainText("verified");
  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  const list = page.getByRole("region", { name: "Private inbox" });
  await expect(list).toContainText(body);
  expect(await list.locator("img").count()).toBe(0);
  await list.getByRole("button", { name: "Mark read" }).first().click();
  await expect(list).toContainText("Read");
  await page
    .getByLabel("Tenant", { exact: true })
    .selectOption("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
  await expect(page.getByLabel("Tenant", { exact: true })).toHaveValue(
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  );
  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Private inbox" }),
  ).not.toContainText(body);
});

test("expiry disables decisions without a reload and unknown state exposes reconciliation", async ({
  page,
}) => {
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.getByTestId("approval-card")).toBeVisible();
  const id = new URL(page.url()).searchParams.get("run_id")!;
  const snapshot = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  // UI clock boundary fixture only; real DB-time expiry/security is covered by F12 integration tests.
  const expired = {
    ...snapshot,
    action: {
      ...snapshot.action,
      expires_at: new Date(Date.now() + 4000).toISOString(),
    },
  };
  await page.route(`**/api/v2/runs/${id}`, (r) => r.fulfill({ json: expired }));
  await page.reload();
  await expect(page.getByTestId("approval-card")).toContainText("Expired", {
    timeout: 10000,
  });
  await expect(
    page.getByRole("button", { name: "Approve & create ticket", exact: true }),
  ).toBeDisabled();
  const unknown = {
    ...snapshot,
    status: "completed",
    outcome: "unknown_outcome",
    action: { ...snapshot.action, execution_status: "unknown" },
    actions: [],
  };
  await page.unroute(`**/api/v2/runs/${id}`);
  await page.route(`**/api/v2/runs/${id}`, (r) => r.fulfill({ json: unknown }));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Reconciliation required" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Check saved reconciliation state" }),
  ).toBeVisible();
});
