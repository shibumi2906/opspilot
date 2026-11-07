import { test, expect } from "../../web/e2e/test";

test.skip(
  process.env.F19_CONTRACT !== "1",
  "Dedicated local real Prometheus profile",
);

test("Prometheus source is investigated through MCP and provenance survives refresh", async ({
  page,
}) => {
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page).toHaveURL(/run_id=[0-9a-f-]+/);
  const id = new URL(page.url()).searchParams.get("run_id")!;
  await expect
    .poll(
      async () => {
        const value = await (
          await page.request.get(`/api/v2/runs/${id}`)
        ).json();
        return value.status;
      },
      { timeout: 45000 },
    )
    .toBe("completed");
  const saved = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  expect(saved.mode).toBe("scripted");
  expect(saved.usage.cost_usd).toBe(0);
  const source = saved.evidence.find(
    (e: { source_type: string }) => e.source_type === "integration_status",
  );
  expect(source.source_version).toBe("prometheus-mapping1:synthetic:fixture");
  expect(source.facts.status).toBe("degraded");
  const expiration = saved.evidence.find(
    (e: { source_type: string }) => e.source_type === "credential_status",
  );
  expect(expiration.facts.status).toBe("unknown");
  expect(
    saved.evidence.some(
      (e: { facts: { event_type?: string } }) =>
        e.facts.event_type === "prometheus.metric.sample",
    ),
  ).toBeTruthy();
  expect(
    saved.report.facts.some((f: { statement: string }) =>
      f.statement.startsWith("Synthetic metrics:"),
    ),
  ).toBeTruthy();
  expect(
    saved.report.facts.some((f: { statement: string }) =>
      f.statement.startsWith("Synthetic Prometheus health sample:"),
    ),
  ).toBeTruthy();
  expect(
    saved.report.facts.some((f: { statement: string }) =>
      f.statement.startsWith("Delivery event:"),
    ),
  ).toBeFalsy();
  expect(saved.action).toBeNull();
  await page
    .locator(".source-button")
    .filter({ hasText: "integration status" })
    .first()
    .click();
  await expect(
    page.getByRole("article", { name: "Evidence detail" }),
  ).toContainText("prometheus-mapping1:synthetic:fixture");
  await page.reload();
  await page
    .locator(".source-button")
    .filter({ hasText: "integration status" })
    .first()
    .click();
  await expect(
    page.getByRole("article", { name: "Evidence detail" }),
  ).toContainText("prometheus-mapping1:synthetic:fixture");
  const after = await (await page.request.get(`/api/v2/runs/${id}`)).json();
  expect(after.evidence).toEqual(saved.evidence);
});
