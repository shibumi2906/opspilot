// Real isolated Full UI only. Authentication happens in unrecorded contexts.
// /video is ignored working storage; /lab is the retained scripted recovery4 profile.
import assert from "node:assert/strict";
import { lookup } from "node:dns/promises";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
} from "node:fs";
import { X509Certificate, createHash, createHmac } from "node:crypto";
import { createRequire } from "node:module";
const { chromium } = createRequire("/app/web/package.json")("playwright");
const json = (path) =>
  JSON.parse(readFileSync(path, "utf8").replace(/^\uFEFF/, ""));
const plan = json("/video/plan.json");
const manifest = json("/lab/release-manifest.json");
assert.equal(manifest.project, "opspilot-full-test-f23-recovery4");
assert.equal(manifest.model, "scripted");
const resuming = process.argv.includes("--resume-evidence");
const previousState = existsSync("/video/capture-state.json")
  ? json("/video/capture-state.json")
  : null;
if (resuming) {
  assert.equal(previousState?.phase, "failed_at_evidence");
  assert.equal(previousState.scenes.length, 2);
  assert(previousState.approved_run && previousState.saved_action);
  assert(!previousState.approved_verified && !previousState.rejected_run);
} else
  assert(
    !previousState,
    "Existing capture state preserved; inspect before resuming",
  );
const credentials = json("/lab/credentials.json"),
  seeds = json("/lab/otp-fixtures.json");
const origin = "https://app.opspilot.localhost:8443",
  issuer = "https://idp.opspilot.localhost:8543";
const request = "Investigate why GreenShop orders fail today";
mkdirSync("/video/raw", { recursive: true });
mkdirSync("/video/frames", { recursive: true });
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
const state = previousState ?? {
  phase: "authentication",
  scenes: [],
  project: manifest.project,
  paid_calls: 0,
  jira_dispatches: 0,
};
function save() {
  writeFileSync("/video/capture-state.json", JSON.stringify(state, null, 2));
}
save();
let stage = "authentication";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function focus(page, locator) {
  await locator.waitFor();
  await locator.evaluate((element) =>
    window.scrollTo({
      top: element.getBoundingClientRect().top + scrollY - 24,
      behavior: "smooth",
    }),
  );
  await page.waitForTimeout(600);
}
async function login(name) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    locale: "en-US",
    timezoneId: "Asia/Jerusalem",
  });
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(origin);
    await page.getByRole("link", { name: "Sign in", exact: true }).click();
    await page.locator("#username").fill(name);
    await page.locator("#password").fill(credentials.user);
    await page.locator("#kc-login").click();
    await page.locator("#otp").waitFor();
    const previous = Math.floor(Date.now() / 30000);
    while (Math.floor(Date.now() / 30000) <= previous) await sleep(250);
    const counter = Buffer.alloc(8);
    counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
    const digest = createHmac("sha1", seeds[name]).update(counter).digest(),
      offset = digest[19] & 15;
    await page
      .locator("#otp")
      .fill(
        String((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(
          6,
          "0",
        ),
      );
    await page.locator("#kc-login").click();
    await page.waitForURL(origin + "/");
    const tenant = page.getByLabel("Tenant", { exact: true });
    await tenant.waitFor();
    if (
      (await tenant.inputValue()) !== "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    ) {
      await tenant.selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
      await page.waitForLoadState("networkidle");
    }
    const me = await page.evaluate(async () =>
      (await fetch("/auth/me")).json(),
    );
    assert(me.roles.includes(name));
    return { storage: await context.storageState(), actor: me.user_id }; // memory only
  } finally {
    await context.close();
  }
}
let identities;
async function open(page, id) {
  await page.goto(origin + (id ? "/?run_id=" + id : "/"));
  await page.getByRole("heading", { name: "Clarity before action." }).waitFor();
  await page.getByLabel("Tenant", { exact: true }).waitFor();
  await page.getByTestId("model-mode").waitFor();
  await page.waitForFunction(
    () =>
      document
        .querySelector('[data-testid="model-mode"]')
        ?.textContent?.trim() === "Scripted model",
  );
  assert.equal(
    (await page.getByTestId("model-mode").innerText()).trim(),
    "Scripted model",
  );
}
async function snapshot(page, id) {
  return page.evaluate(async (run) => {
    const r = await fetch("/api/v2/runs/" + run);
    if (!r.ok) throw Error("Snapshot unavailable");
    return r.json();
  }, id);
}
async function waitSnapshot(page, id, status) {
  for (let i = 0; i < 240; i++) {
    const value = await snapshot(page, id);
    if (value.status === status) return value;
    assert(
      !["failed", "needs_attention", "cancelled"].includes(value.status),
      "Workflow needs review; no retry",
    );
    await sleep(500);
  }
  throw Error("Saved result timeout; operation must not be repeated blindly");
}
async function startRun(page, field) {
  await page.getByLabel("What needs attention?").fill(request);
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await page.waitForURL((url) => url.searchParams.has("run_id"));
  const id = new URL(page.url()).searchParams.get("run_id");
  assert.match(id, /^[a-f0-9-]{36}$/);
  state[field] = id;
  state.phase = field + "_created";
  save();
  const value = await waitSnapshot(page, id, "waiting_for_approval");
  assert.equal(
    value.action.tool_name,
    "create_ticket",
    "Only local ticket proposals allowed",
  );
  return value;
}
async function scene(key, role, setup, perform = async () => {}) {
  if (state.scenes.some((s) => s.key === key)) return;
  stage = key;
  const item = plan.scenes.find((s) => s.key === key);
  assert(item);
  const context = await browser.newContext({
    storageState: identities[role].storage,
    viewport: { width: 1280, height: 720 },
    locale: "en-US",
    timezoneId: "Asia/Jerusalem",
    recordVideo: { dir: "/video/raw", size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const video = page.video();
  try {
    await setup(page);
    assert(page.url().startsWith(origin + "/"));
    const begin = Date.now();
    await perform(page, item);
    await sleep(
      Math.max(0, item.duration_seconds * 1000 - (Date.now() - begin)),
    );
    assert(page.url().startsWith(origin + "/"), "Never publish IdP screens");
    await page.screenshot({ path: "/video/frames/" + key + ".png" });
    const seconds = (Date.now() - begin) / 1000;
    await context.close();
    const raw = await video.path();
    renameSync(raw, "/video/raw/" + key + ".webm");
    state.scenes.push({
      key,
      role,
      content_seconds: seconds,
      source: "raw/" + key + ".webm",
      frame: "frames/" + key + ".png",
    });
    state.phase = key + "_recorded";
    save();
    console.log(JSON.stringify({ scene: key, recorded: true }));
  } catch (error) {
    await context.close();
    throw error;
  }
}
try {
  identities = {
    operator: await login("operator"),
    approver: await login("approver"),
  };
  assert.notEqual(identities.operator.actor, identities.approver.actor);
  await scene(
    "workspace",
    "operator",
    (page) => open(page),
    async (page) => {
      await page.getByLabel("Tenant", { exact: true }).hover();
      await sleep(3500);
      await page.getByRole("button", { name: "History", exact: true }).hover();
    },
  );
  await scene(
    "investigate",
    "operator",
    (page) => open(page),
    async (page) => {
      const pending = await startRun(page, "approved_run");
      state.saved_action = {
        id: pending.action.action_id,
        hash: pending.action.arguments_hash,
      };
      save();
    },
  );
  await scene(
    "evidence",
    "operator",
    (page) => open(page, state.approved_run),
    async (page, item) => {
      const panel = page.locator(".evidence-panel");
      await focus(page, panel);
      await panel
        .locator(".source-button")
        .filter({ hasText: /credential status/i })
        .first()
        .click();
      await focus(page, page.locator("#evidence-detail"));
      await sleep(item.duration_seconds * 450);
      await page.getByRole("button", { name: /Close/ }).click();
      await focus(page, page.locator(".hypothesis").first());
    },
  );
  await scene(
    "approval",
    "operator",
    (page) => open(page, state.approved_run),
    async (page, item) => {
      const card = page.getByTestId("approval-card");
      await focus(page, card);
      assert(
        await card
          .getByRole("button", { name: "Approve & create ticket" })
          .isDisabled(),
      );
      await sleep(item.duration_seconds * 500);
      await focus(page, card.locator(".decision-buttons"));
    },
  );
  await scene(
    "persisted",
    "operator",
    (page) => open(page, state.approved_run),
    async (page) => {
      const value = await snapshot(page, state.approved_run);
      assert.equal(value.status, "waiting_for_approval");
      assert.equal(value.action.action_id, state.saved_action.id);
      assert.equal(value.action.arguments_hash, state.saved_action.hash);
      const card = page.getByTestId("approval-card");
      await card.getByText("Saved action & integrity", { exact: true }).click();
      await focus(page, card.getByTestId("action-id"));
      state.same_saved_action_verified = true;
      save();
    },
  );
  await scene(
    "approver",
    "approver",
    (page) => open(page, state.approved_run),
    async (page, item) => {
      await sleep(3000);
      const card = page.getByTestId("approval-card");
      await focus(page, card);
      assert(
        await card
          .getByRole("button", { name: "Approve & create ticket" })
          .isEnabled(),
      );
      await sleep(item.duration_seconds * 400);
      await focus(page, card.locator(".decision-buttons"));
    },
  );
  await scene(
    "verified",
    "approver",
    async (page) => {
      await open(page, state.approved_run);
      await focus(
        page,
        page.getByTestId("approval-card").locator(".decision-buttons"),
      );
    },
    async (page, item) => {
      await sleep(1500);
      state.phase = "approval_submitted_once";
      save();
      await page
        .getByRole("button", { name: "Approve & create ticket" })
        .click();
      const done = await waitSnapshot(page, state.approved_run, "completed");
      assert.equal(done.outcome, "actions_verified");
      state.approved_verified = true;
      save();
      await page
        .getByRole("heading", { name: "Ticket verified.", exact: true })
        .waitFor();
      const report = page.getByRole("region", { name: "Final report" });
      await focus(page, report);
      assert.equal(
        (await report.getByTestId("verification-status").innerText())
          .trim()
          .toLowerCase(),
        "verified",
      );
      await sleep(Math.max(0, item.duration_seconds * 400));
      await focus(page, report.getByTestId("verification-status"));
    },
  );
  await scene(
    "history",
    "operator",
    async (page) => {
      await open(page);
      await page.getByRole("button", { name: "History", exact: true }).click();
      await page
        .getByRole("heading", { name: "Investigation history", exact: true })
        .waitFor();
    },
    async (page, item) => {
      await page
        .getByLabel("Search requests", { exact: true })
        .fill("GreenShop");
      await page
        .getByRole("button", { name: "Apply filters", exact: true })
        .click();
      await page.locator(".workspace-list li").first().waitFor();
      await sleep(item.duration_seconds * 450);
      await page
        .locator(".workspace-list li")
        .first()
        .getByRole("button")
        .click();
      await page.waitForURL(
        (url) => url.searchParams.get("run_id") === state.approved_run,
      );
      assert.equal(
        (await snapshot(page, state.approved_run)).outcome,
        "actions_verified",
      );
    },
  );
  // A separate new investigation is prepared off-camera; its rejection is recorded.
  const setup = await browser.newContext({
    storageState: identities.operator.storage,
  });
  try {
    const page = await setup.newPage();
    await open(page);
    await startRun(page, "rejected_run");
  } finally {
    await setup.close();
  }
  await scene(
    "rejected",
    "approver",
    (page) => open(page, state.rejected_run),
    async (page, item) => {
      const card = page.getByTestId("approval-card");
      await focus(page, card);
      await sleep(3000);
      await focus(page, card.getByRole("button", { name: "Reject action" }));
      state.phase = "rejection_submitted_once";
      save();
      await card.getByRole("button", { name: "Reject action" }).click();
      const done = await waitSnapshot(page, state.rejected_run, "completed");
      assert.equal(done.outcome, "rejected");
      assert(!done.report?.ticket_id);
      state.rejected_without_ticket = true;
      save();
      await page
        .getByRole("heading", { name: "Decision respected.", exact: true })
        .waitFor();
      await focus(page, page.getByRole("region", { name: "Final report" }));
    },
  );
  assert.equal(state.scenes.length, 9);
  state.phase = "complete";
  save();
  writeFileSync(
    "/video/recording.json",
    JSON.stringify(
      {
        ...state,
        authentication_recorded: false,
        recording_viewport: { width: 1280, height: 720 },
        synthetic: true,
        model: "scripted",
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      passed: true,
      recorded_scenes: 9,
      approved_local_tickets: 1,
      rejected_runs: 1,
    }),
  );
} catch (error) {
  state.phase = "failed_at_" + stage;
  state.failure_type = error.name;
  save();
  writeFileSync("/video/private-error.txt", String(error.stack));
  console.error(
    "Full video capture stopped at " +
      stage +
      "; private state retained, no automatic operation retry",
  );
  process.exitCode = 1;
} finally {
  await browser.close();
}
