import { test, expect } from "../../web/e2e/test";

test("expired workflow content has an explicit terminal presentation", async ({ page }) => {
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
  await page.getByRole("button", { name: "Start investigation", exact: true }).click();
  await expect(page.getByTestId("approval-card")).toBeVisible();
  const id = new URL(page.url()).searchParams.get("run_id")!;
  const snapshot = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  // Presentation fixture only. Real erasure, tombstones, isolation and HTTP DTOs
  // are verified against PostgreSQL/MCP/API in test_lifecycle.py.
  const archived = {
    ...snapshot, status: "completed", request: "", action: null, actions: [], plan: null,
    evidence: [], timeline: [], hypotheses: [], report: null,
    retention: { evidence_removed: true, history_removed: true, audit_removed: true },
  };
  await page.route(`**/api/v2/runs/${id}`, route => route.fulfill({ json: archived }));
  await page.reload();
  await expect(page.getByRole("status").filter({ hasText: "project retention policy" })).toBeVisible();
  await expect(page.getByText("Completed operations remain recorded.", { exact: false })).toBeVisible();
  await expect(page.getByTestId("approval-card")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve & create ticket", exact: true })).toHaveCount(0);
});
