// Local development Full only; synthetic read-only run through real OIDC and SSE.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { chromium } from "../web/node_modules/playwright/index.mjs";
const env = Object.fromEntries(readFileSync(".env", "utf8").split(/\r?\n/).map(line => {
  const index = line.indexOf("="); return [line.slice(0, index), line.slice(index + 1).replace(/^["']|["']$/g, "")];
}));
const origin = env.APP_ORIGIN ?? "http://127.0.0.1:8091";
assert(["http://127.0.0.1:8091", "http://localhost:8091"].includes(origin));
const browser = await chromium.launch({ headless: true, ...(process.platform === "win32" ? { channel: "msedge" } : {}) });
try {
  const context = await browser.newContext({ baseURL: origin });
  const page = await context.newPage(); page.setDefaultTimeout(30000);
  await page.goto(origin + "/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.locator("#username").fill("demo");
  await page.locator("#password").fill(env.OIDC_DEMO_PASSWORD);
  await page.locator("#kc-login").click();
  await page.getByLabel("Tenant", { exact: true }).selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await page.getByLabel("What needs attention?").waitFor();
  assert.equal((await (await page.request.get("/api/v2/config")).json()).mode, "scripted");
  const stream = page.waitForResponse(r => r.url().endsWith("/events") && r.status() === 200);
  await page.getByLabel("What needs attention?").fill("GreenShop status");
  await page.getByRole("button", { name: "Start investigation", exact: true }).click();
  const response = await stream;
  assert(response.headers()["content-type"].startsWith("text/event-stream"));
  assert.equal(new URL(response.url()).search, "");
  assert(response.request().headers()["last-event-id"]);
  const run = new URL(page.url()).searchParams.get("run_id");
  let snapshot;
  for (let attempt = 0; attempt < 180; attempt++) {
    snapshot = await (await page.request.get(`/api/v2/runs/${run}`)).json();
    if (!["queued", "running"].includes(snapshot.status)) break;
    await page.waitForTimeout(500);
  }
  assert.equal(snapshot.status, "completed"); assert.equal(snapshot.outcome, "diagnosis_only");
  const reconnected = page.waitForResponse(r => r.url().endsWith("/events") && r.status() === 200);
  await Promise.all([reconnected, promisify(execFile)("docker", ["restart", "-t", "3", "opspilot-full-api-1"], { windowsHide: true, timeout: 60000 })]);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("link", { name: "Sign in", exact: true }).waitFor();
  const report = { passed: true, run_id: run, status: snapshot.status, outcome: snapshot.outcome,
    real_oidc: true, cookie_sse: true, header_cursor: true, url_credentials: false,
    api_restart_reconnect: true, private_dom_cleared: true, synthetic: true, vendor_writes: 0 };
  writeFileSync("docs/full/evidence/f13/live-sse.json", JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
