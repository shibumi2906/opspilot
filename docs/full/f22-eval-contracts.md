# F22 eval and release contracts

Owner authorized F22 separately on 2026-11-08, base `e1674e6`, despite F20/F21
blockers. This supersedes historical “do not start F22” directions only for F22.
No paid calls, Jira activity, remote CI, push, main Full rebuild/migration/seed or
F23/F24 work is authorized by this stage.

## Frozen corpus

`src/opspilot/evals/full-cases.json` contains exactly 50 ordered identities:
10 lookup/status, 12 investigation, 8 approval, 8 policy/injection/access,
6 infrastructure and 6 ambiguity/insufficient-data. Both seeded tenants and RU/EN
are represented. `full-split.json` fixes 30 dev / 20 holdout memberships and corpus
SHA256 before execution. Prompts were not tuned. The public holdout was inspected
while implementing and debugging the harness: **not unseen**. Future prompt tuning
must not present this holdout as an untouched quality measurement.

The original 12-case corpus/schema/assertions/runner/report remain byte-equivalent
to the base after newline normalization. Their results remain a separate group.
Full cases reuse explicit synthetic fixture expectations; this is a bounded fixture
sample, not a production-distribution quality estimate. The 50 corpus cases use
single-ticket v1 workflows. Separate mixed-plan/cancellation regression evidence
exercises per-action v2 effects; those assertions do not inflate the 50 denominator.

## Execution and assertions

`tests/f22_lab.py` is a test harness, not a production runtime entry point. BFF
requests use ASGI HTTP through real session/CSRF middleware, role checks and routes.
Sessions are inserted with the existing test-only identity helper. Operator creates,
distinct approver decides, and durable worker claim/execute/finish runs in process.
MCP uses an actual native TCP server, signed service requests, PostgreSQL role/RLS,
Redis and the independent TLS manager. This does not claim process isolation,
real IdP login, live connector reads, HA or F20 Jira write boundaries.

Each case records public snapshot, source types/IDs, checkpoint evidence, LLM-selected
reads separately from verification calls, immutable action outcome, durable job
status/attempts and DB predicates. Canonical predicates reject unsupported facts,
false verified success, forbidden selection, duplicate/unauthorized writes and writes
before decision. HTTP probes include operator-decision denial, cross-tenant reads,
anonymous reads and missing-CSRF rejection. Existing negative eval unit tests mutate
results to show safety checks reject unsafe outcomes.

The runner validates all five DSNs and actual `current_database()`, holds an advisory
lock, and executes every scheduled identity. A diagnostic limit produces an incomplete
failed gate. Exceptions persist safe class names and harness-owned assertion codes;
provider bodies, headers and connection strings are excluded. Checkpoint inspection
uses the persisted actor's existing `execution_scope`; RLS/fences are not bypassed.

## Real and human gates

Scripted is the default; Compose explicitly blanks `OPENAI_API_KEY`. No real execution
occurred. The harness has an explicit `--mode real --authorize-real` entry point for a
future separately authorized operator with local credentials and fixed model. Merely
setting a provider key does not select real mode. Unauthorized real execution fails
before settings/credentials/database access. Do not execute that entry point under the
current owner's prohibition of paid calls.

The real schedule is 30 dev once + 20 holdout three times = **90**, 50 distinct.
Repeat 1 of each holdout belongs to its three repeats; there is no fourth run.
All attempts remain in order; no best-of selection. Unknown usage/spend remains unknown;
known recorded spend is separately totalled. Human facts/hypotheses review is a pending
queue, not an automatic judgment. Even 90 successful model executions cannot close
human review, security or dependent live gates.

## SEC-01/10/11

The 253 inherited ASVS rows, identities, owners, baseline/N/A fields are untouched;
`asvs-baseline.json` compares the entire backlog to `e1674e6`. Per-case ASVS IDs are
validated against that backlog. Policy/injection/tenant probes support ASVS access
controls (`v5.0.0-8.1.1`, `8.2.1`); source/claim handling and protected evidence also
require the inherited encoding/logging controls, not an assertion of chapter closure.

Ruff, scoped mypy, frozen locks, isolated Compose config, exact-secret scans, Python
dependency audit and fresh archive-config-verified image scans are separate gates.
Known manager HIGH `CVE-2026-78661`, x/net0.61.0 (fix0.62.0), remains applicable with
no exception. No manager rebuild/pruning was performed. Full security, Pilot and whole
ASVS L2 remain **NOT_MET**.

## Reproduction

PowerShell from Ops, with existing independent private test prerequisites:

```powershell
./scripts/test-full-f22.ps1 -Mode Prepare -Project opspilot-full-test-f22-r2 -Subnet 35
./scripts/test-full-f22.ps1 -Mode Scripted -Project opspilot-full-test-f22-r2 -Subnet 35
./scripts/test-full-f22.ps1 -Mode Regression -Project opspilot-full-test-f22-r2 -Subnet 35
./scripts/test-full-f22.ps1 -Mode Units -Project opspilot-full-test-f22-r2 -Subnet 35
./scripts/test-full-f22.ps1 -Mode Security
./scripts/test-full-f22.ps1 -Mode Stop -Project opspilot-full-test-f22-r2 -Subnet 35
```

Use a fresh project for Prepare; retained test volumes are evidence. Manager tokens
expire after one hour; explicit `setup-full-f22-manager.py --project ...` refreshes
that lab without replacing its keys. Network subnet overlap is rejected by preflight.
The accepted local lab is r1/subnet34/schema0021; main Full stays schema0019.
Avoid overwriting accepted evidence for later reproduction; archive report directories
first and use a new report mount override. Existing F21 reports remain historical.

`.github/workflows/f22.yml` is a manual workflow. Its initializer refuses execution
outside ephemeral GitHub-hosted runners and refuses an existing `.env`/service key
ring. It builds isolated images, runs 50+12, preserves reports and fails on raw
HIGH/CRITICAL findings. The current known HIGH is not an allowlisted pass. Workflow
preparation and local shell/config validation do not constitute remote CI execution.
Secrets/private logs/manager recovery state are never uploaded.

F20 remains blocked on unimplemented dispatch/one-attempt/reconciliation and deferred
real Jira gates; F21 functional checks passed but overall remains blocked on those
boundaries and manager security. F22 does not close either stage. F22 itself remains
blocked on these dependencies, real/human/remote-CI gates and security.
