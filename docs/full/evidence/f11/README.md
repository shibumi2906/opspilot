# F11 — bounded mixed plans, dependencies and approval waves

Status: **done**, 28 October 2026. Base F10 `efc6f1b`. Only F11 completed;
F12–F24 remain not_started. Canonical Full worktree/branch preserved, MVP isolated.
Schema `0013_mixed_plans`; mixed workflows pinned to `full-graph-v2`, compatible `full-graph-v1`
retained for previous checkpoints and ordinary single-action runs. State/DTO/revision schema1,
checkpoint SDK migration9. Complete ASVS L2 remains **NOT_MET**.

## Result and authority boundary

- Typed local DAG: at most3 actions,2 dependencies/node,2 approval waves,40KB stored plan.
  Unknown tools/fields/dependencies, cycles, duplicate keys/intents and cross-customer scope fail.
- One immutable plan per run, stable UUID business-intent slots and plan digest. Identical prepare
  reuses existing intents; changed prepare conflicts, including after completed effects.
- Every concrete action gets its own immutable revision, persisted human decision and independent
  signed short-lived execution grant. Plan/slot/hash/wave/dependencies bind into revision digest.
  Core checks eligibility before grant issuance; MCP independently checks its persisted ledger
  inside the local write transaction. One approval never authorizes a sibling or future wave.
- Partial decisions persist as approval/event only. Execution waits for every decision in that
  wave, then processes approved eligible actions sequentially. Rejected/unknown/mismatching
  prerequisites skip dependents. Unknown effects are not blindly retried.
- Deferred comment has no executable action/approval until its ticket is independently verified.
  Core binds the actual ticket ID, creates a distinct revision/card, and waits for a second decision.
- At most3 verification reservations per action are persisted and fenced in PostgreSQL; crash or
  service restart does not reset them. Completed verified slots are reused without dispatch.
- A bounded resume successor preserves a second-wave decision arriving after its interrupt
  checkpoint but before the previous resume job acknowledgment.
- Snapshot/UI include per-slot state and all concrete action cards. Report lists each decision,
  effect and verification; partial plans use actions_partially_verified, never global verified success.

Explicit local mixed requests such as `Investigate GreenShop and notify manager and add a ticket
comment` use the new graph. Model output must exactly match the trusted Core-generated scoped plan;
no model-supplied recipient, URL, future ticket ID or extra capability is accepted. Local notification
routing selects the first enabled configured tenant approver from a bounded10 membership candidates.
It confirms internal inbox persistence, not external delivery or human reading. A full plan editor,
customer-specific recipient administration/inbox UI, F12 freshness/replan and F14 full UI are not claimed.
Bound plan revisions are immutable in F11; legacy v1 revision API remains supported.

Security SEC-01/03/07/10: [contracts](../../f11-security-contracts.md),
[requirement backlog](../../../security/asvs-l2-requirement-backlog.json). New storage is tenant
FORCE RLS, immutable intent metadata, composite tenant references and fenced status/quota updates.
MCP has no direct SELECT on plan storage; only the constrained independent checker. Plan events
carry identifiers/status/wave, no bodies or grants. New views preserve F10 JSON/text allowlists,
existing object authorization, CSRF/origin/session/MFA and independent actor/approver checks.
All253 ASVS IDs/levels/baseline assessments and accountable owners remain unchanged. Local scoped
contributions do not close whole norms or owner-reviewed N/A. Future operational controls remain.

## Measured acceptance

[checks.json](checks.json), [release log](checks.log), [installed app/source check](image-source-check.json).

| Gate | Result |
| --- | --- |
| Full backend on fresh verified DB | 351 passed / 9 dedicated skips |
| Focused F11 real graph/PostgreSQL/MCP | 8 passed, included in backend |
| Additional mixed cancellation regression | 2 passed on same final app image, test file mounted read-only |
| Host unit | 126 passed, included in backend |
| Ruff/format/mypy | pass,115 application source files; operational scripts also checked |
| TypeScript/Vite | pass |
| Real browser/OIDC | 14/14, including2 new mixed UI cases |
| Durable queue process | 5 passed |
| Fencing kill/stop/TCP partition | 3 passed |
| Fresh native TLS/MFA | 8 TLS probes +11 browser/security checks |
| Scripted evals | 12/12; hard safety gate true |
| Runtime app/web SCA | 0 findings |
| Python89 distributions/npm audit | 0 findings |

Evidence: [focused](focused.log), [mixed cancellation](cancellation.log),
[DB plan/RLS/quota/receipt checks](db-security.json), [grant/audit privileges](grant-security.json),
[process faults](process/), [TLS probes](tls/tls-probes.json), [TLS/MFA browser](tls/browser.json),
[TLS log](tls-checks.log), [eval JSON](evals/scripted.json), [eval report](evals/scripted.md),
[app SCA](security/app-image.json), [web SCA](security/web-image.json),
[Python audit](security/python-audit.json), [npm audit](security/npm-audit.json).

F11 scenarios include both approve-ticket/reject-inbox and inverse mixtures, all rejected,
skipped dependents, concrete ticket→new comment card→separate decision, cycle/unknown dependency,
concurrent independent decisions, plan replay/conflict, DB verification quota across restart,
actual child-worker os._exit(99) between actions, and next-wave decision racing worker ack.
A test-minted valid signed **persisted** grant still fails in MCP while a sibling decision is pending,
without consuming it or creating an effect. Cancellation before dispatch and after first-wave
completion preserves every completed ticket/notification and never sends the deferred comment.
Scripted eval unauthorized writes/duplicates/false verified success are0. These12 inherited cases
are not the future F22 real/holdout evaluation gate.

Commands from Full worktree:

```powershell
./scripts/test-full-f11.ps1
# default isolated project: opspilot-full-test-f11-verified
./scripts/test-full-f11.ps1 -SkipBuild -Project opspilot-full-test-f11-verified
# additional cancellation check on the same final runtime:
docker compose --env-file .env -p opspilot-full-test-f11-verified -f compose.full.yaml -f compose.full.test.yaml run --rm -v "${PWD}/tests:/app/tests:ro" tests python -m pytest -p no:cacheprovider -q tests/integration/test_plan_cancellation.py
.venv/Scripts/python.exe -m pytest -q tests/unit
.venv/Scripts/ruff.exe check src tests scripts/check-f11-security-state.py scripts/smoke-full-f11.py
.venv/Scripts/ruff.exe format --check src tests scripts/check-f11-security-state.py scripts/smoke-full-f11.py
.venv/Scripts/mypy.exe --cache-dir .tools/f11-mypy src
# from web: npm run build
```

The fresh verified test project uses opspilot_full_test and no published ports. Additional
cancellation tests were added after the full351-case run, executed separately with a read-only
source mount against the same final application code. A fresh rebuild from this commit includes
those2 cases in ordinary full discovery. No application source changed between these runs.
Fresh TLS profile opspilot-full-security-f11 uses separate generated .tools/security-f11 credentials,
keys/CA and volumes. It follows scripts/test-security-local.ps1 with that project/compose path,
-SkipBuild and -ReportDir docs/full/evidence/f11/tls (local .tools/f11-tls.ps1 wrapper).
No secret-bearing compose/env is committed. [Artifact credential check](artifact-secret-check.json).

## Failed candidates, preserved honestly

- [Partial-decision candidate](partial-decision-candidate.log): unfenced updated_at-only change
  on a waiting run was correctly rejected by F06. Partial decisions now persist approval/events
  without updating the run until the wave is complete; fencing was not weakened.
- [Test context](test-context-candidate.log) and [test snapshot](test-detach-candidate.log): fixed
  test-only async/sync context-manager usage and a detached expired ORM object; scenario assertions retained.
- [Collection candidate](collection-candidate.log): unit/integration filenames collided in pytest;
  unit file renamed to test_mixed_plan_contracts.py.
- [Legacy-null candidate](legacy-null-candidate.log): new JSONB field stored Python None as JSON null,
  while SQL gate tested SQL NULL. It denied legacy actions (65 failures), not unauthorized writes.
  ORM now uses none_as_null; SQL defensively recognizes both absent representations and still denies
  any unbound action belonging to a run that has a plan. Full351 and all security/browser gates
  passed on a fresh verified DB after the fix.

The earlier opspilot-full-test-f11-release DB is a retired development candidate; its volumes are
preserved, but it is not the canonical verified profile. Default release project now explicitly uses
opspilot-full-test-f11-verified. No assertion, role privilege, time bound or acceptance gate was relaxed.
The temporary approval-review usage failure executed no command; continuation used the same normal
approval mechanism after the owner asked to continue. No approval bypass occurred.

## Live upgrade and preservation

[Upgrade](upgrade.json): Full012→013 preserved counts and SHA-256 of tickets/comments/notifications
and existing action/receipt rows (new optional plan_binding excluded from pre/post row fingerprint).
[Live](live.json): ordinary v1 read-only diagnosis and new v2 mixed run both complete; actual2 waves,
3 independently verified receipts, replay returns the same run, MCP13 tools.
[Readiness](restored-full.json): two workers healthy, UI8091/API8011 HTTP200.
Live probe scripts/smoke-full-f11.py is mounted read-only into the ordinary Full api container.

MVP [before](mvp-before.json) and [final](mvp-isolation.json): all184 source/media/docs/env
fingerprints, main/HEAD, image tags, volume metadata and read-only content match the saved baseline.
Original checkout clean; F01 baseline timing limitation remains explicit in preservation evidence.
MVP was not changed, built, migrated or intentionally started. No Docker restart was required in F11.
[Cleanup](cleanup.json): candidate/verified test and TLS containers/networks removed, volumes/images
retained. Application calls were only local synthetic OIDC/PostgreSQL/MCP; dependency/scanner
downloads occurred. Paid model/provider/vendor writes, remote CI, production deployment and push0.

[source-tree.json](source-tree.json) binds actual tested worktree content; [images](images.json).
Evals record the dirty F10 parent SHA, not a claim of testing its clean commit. All115 installed
application files match final source. Logs normalize trailing whitespace for diff checks; raw output
remains ignored in .tools. F12/F14/F15 functionality was not silently included or declared done.

Blockers F11: none. Local stage commit subject:
`feat(full-f11): implement bounded mixed plans and approval waves`.
