// Actual Full UI, synthetic local data. No IdP screens, tokens, HARs or storage dumps.
// Run only through the prepared F23 browser service; /lab and /screens are mounts.
import assert from "node:assert/strict";
import { lookup } from "node:dns/promises";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { X509Certificate, createHash, createHmac } from "node:crypto";
import { createRequire } from "node:module";

const { chromium } = createRequire("/app/web/package.json")("playwright");
const credentials = JSON.parse(readFileSync("/lab/credentials.json"));
const seeds = JSON.parse(readFileSync("/lab/otp-fixtures.json"));
const origin = "https://app.opspilot.localhost:8443";
const issuer = "https://idp.opspilot.localhost:8543";
const manifest = JSON.parse(readFileSync("/lab/release-manifest.json"));
const resume = process.argv.includes("--resume");
const saved = resume ? JSON.parse(readFileSync("/capture-state.json")) : null;
assert.equal(manifest.model, "scripted");
assert.equal(manifest.project, "opspilot-full-test-f23-recovery4");
const outputs = [
  "workspace.png",
  "approval.png",
  "verified.png",
  "history.png",
  "capture.json",
];
for (const name of outputs.filter(
  (name) => !resume || !["workspace.png", "approval.png"].includes(name),
)) {
  assert(!existsSync("/screens/" + name), "Existing screenshots preserved");
}
const pins = ["app.opspilot.localhost", "idp.opspilot.localhost"]
  .map((name) =>
    createHash("sha256")
      .update(
        new X509Certificate(
          readFileSync("/lab/" + name + ".crt"),
        ).publicKey.export({ type: "spki", format: "der" }),
      )
      .digest("base64"),
  )
  .join(",");
const browser = await chromium.launch({
  args: [
    "--ignore-certificate-errors-spki-list=" + pins,
    "--host-resolver-rules=MAP app.opspilot.localhost " +
      (await lookup("web")).address +
      ", MAP idp.opspilot.localhost " +
      (await lookup("oidc")).address,
  ],
});
const contexts = [];
let stage = "sign-in";
let activePage;
async function login(name) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1040 },
    deviceScaleFactor: 1,
  });
  contexts.push(context);
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  await page.goto(origin);
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  assert(page.url().startsWith(issuer));
  await page.locator("#username").fill(name);
  await page.locator("#password").fill(credentials.user);
  await page.locator("#kc-login").click();
  await page.locator("#otp").waitFor();
  // Each separate capture process waits for a fresh TOTP window. Re-opening an
  // already completed run must not reuse the factor from the previous attempt.
  const previousWindow = Math.floor(Date.now() / 30000);
  while (Math.floor(Date.now() / 30000) <= previousWindow) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac("sha1", seeds[name]).update(counter).digest();
  const offset = digest[19] & 15;
  const otp = String(
    (digest.readUInt32BE(offset) & 0x7fffffff) % 1000000,
  ).padStart(6, "0");
  await page.locator("#otp").fill(otp);
  await page.locator("#kc-login").click();
  await page.waitForURL(origin + "/");
  const tenant = page.getByLabel("Tenant", { exact: true });
  await tenant.waitFor();
  if ((await tenant.inputValue()) !== "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") {
    await tenant.selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Tenant", { exact: true }).waitFor();
  }
  await page.getByRole("heading", { name: "Clarity before action." }).waitFor();
  assert.equal(
    await page.getByTestId("model-mode").innerText(),
    "Scripted model",
  );
  return page;
}
async function screenshot(page, name, locator = page) {
  assert(
    page.url().startsWith(origin + "/"),
    "Capture only the authenticated app, never the IdP",
  );
  await page.evaluate(() => document.fonts.ready);
  await locator.screenshot({
    path: "/screens/" + name,
    animations: "disabled",
  });
}
try {
  const operator = await login("operator");
  let approver, id;
  if (resume) {
    assert.equal(saved.status, "completed");
    assert.equal(saved.outcome, "actions_verified");
    id = saved.id;
    assert.match(id, /^[a-f0-9-]{36}$/);
    approver = operator;
    await approver.goto(origin + "/?run_id=" + id);
    const snapshot = await approver.evaluate(
      async (run) => (await fetch("/api/v2/runs/" + run)).json(),
      id,
    );
    assert.equal(snapshot.status, "completed");
    assert.equal(snapshot.outcome, "actions_verified");
    assert.equal(snapshot.action.tool_name, "create_ticket");
  } else {
    await screenshot(operator, "workspace.png");
    stage = "new synthetic investigation";
    await operator
      .getByLabel("What needs attention?")
      .fill("Investigate why GreenShop orders fail today");
    await operator
      .getByRole("button", { name: "Start investigation", exact: true })
      .click();
    await operator.waitForURL((url) => url.searchParams.has("run_id"));
    id = new URL(operator.url()).searchParams.get("run_id");
    assert.match(id, /^[a-f0-9-]{36}$/);
    const card = operator.getByTestId("approval-card");
    await card.waitFor({ timeout: 120000 });
    const snapshot = await operator.evaluate(async (run) => {
      const response = await fetch("/api/v2/runs/" + run);
      if (!response.ok) throw Error("Snapshot unavailable");
      return response.json();
    }, id);
    assert.equal(snapshot.status, "waiting_for_approval");
    assert.equal(
      snapshot.action.tool_name,
      "create_ticket",
      "Only a local ticket may be demonstrated",
    );
    assert(
      await card
        .getByRole("button", { name: "Approve & create ticket" })
        .isDisabled(),
    );
    stage = "separate approver";
    approver = await login("approver");
    await approver.goto(origin + "/?run_id=" + id);
    const approvedCard = approver.getByTestId("approval-card");
    await approvedCard.waitFor();
    assert(
      await approvedCard
        .getByRole("button", { name: "Approve & create ticket" })
        .isEnabled(),
    );
    await screenshot(approver, "approval.png", approvedCard);
    stage = "verified local effect";
    await approvedCard
      .getByRole("button", { name: "Approve & create ticket" })
      .click();
    await approver
      .getByRole("heading", { name: /^(Ticket|Plan) verified\.$/ })
      .waitFor({ timeout: 120000 });
  }
  stage = "saved verified result";
  activePage = approver;
  await approver
    .getByRole("heading", { name: /^(Ticket|Plan) verified\.$/ })
    .waitFor({ timeout: 30000 });
  const report = approver.getByRole("region", { name: "Final report" });
  assert.equal(
    (await report.getByTestId("verification-status").innerText())
      .trim()
      .toLowerCase(),
    "verified",
  );
  await screenshot(approver, "verified.png", report);
  stage = "history";
  await operator.getByRole("button", { name: "History", exact: true }).click();
  await operator
    .getByRole("heading", { name: "Investigation history" })
    .waitFor();
  await operator.locator(".workspace-list li").first().waitFor();
  await screenshot(operator, "history.png");
  const hashes = Object.fromEntries(
    outputs
      .filter((name) => name.endsWith(".png"))
      .map((name) => [
        name,
        createHash("sha256")
          .update(readFileSync("/screens/" + name))
          .digest("hex"),
      ]),
  );
  const evidence = {
    captured_at_utc: new Date().toISOString(),
    profile: manifest.project,
    synthetic: true,
    model: "scripted",
    actual_application_ui: true,
    authentication:
      "OIDC password + TOTP, separate operator and approver contexts",
    tls_policy: "two exact generated leaf SPKIs; no global certificate bypass",
    operator_approval_denied: true,
    approver_approval_enabled: true,
    demonstrated_effect:
      "one newly approved local create_ticket; no Jira enrollment or dispatch",
    verification: "verified",
    screenshot_sha256: hashes,
    completed_result_captured_after_read_only_resume: resume,
  };
  writeFileSync(
    "/screens/capture.json",
    JSON.stringify(evidence, null, 2) + "\n",
    { flag: "wx" },
  );
  console.log(
    JSON.stringify({
      passed: true,
      screenshots: 4,
      model: "scripted",
      effect: "local create_ticket",
    }),
  );
} catch (error) {
  if (existsSync("/debug") && activePage?.url().startsWith(origin + "/")) {
    writeFileSync("/debug/showcase-capture-error.txt", String(error.stack));
    await activePage.screenshot({ path: "/debug/showcase-capture-error.png" });
  }
  console.error(
    "Showcase capture failed at " +
      stage +
      "; partial images preserved, no automatic retry",
  );
  process.exitCode = 1;
} finally {
  for (const context of contexts) await context.close();
  await browser.close();
}
