# F10 — local ticket/comment/internal inbox operations

Status: **done**, 28 October 2026. Base F09: `278d92d`. Only F10 completed;
F11–F24 remain not_started. Full worktree and branch stay canonical; MVP remains separate.
Schema `0012_local_operations`; workflow `full-graph-v1`, state/DTO/revision schema1,
checkpoint SDK migration9. Complete ASVS L2 is still **NOT_MET**, not a local-stage claim.

## Result

Three local writes: create_ticket, add_ticket_comment, notify_manager. New reads:
get_ticket_comment/get_notification. Immutable revisions, independent signed execution grants and
service contexts bind the exact tool and approved customer/ticket/recipient/body/evidence fields.
MCP independently checks live persisted approval/roles/ownership/TTL/fence/cancellation.
Comments require an existing same-tenant ticket for the approved customer and target access;
notifications require an existing enabled tenant member. There is no external delivery.

Grant consumption + domain row + receipt commit together. Concurrent replay returns one object;
rollback leaves no consumed grant/orphan effect. Lost response recovers the committed receipt.
Independent MCP reads compare every approved field plus origin operation/generated ID/time.
Missing verification remains unknown, mismatch partial; neither becomes verified success.

Migration0012 adds FORCE-RLS tables, composite tenant references, immutable exact-field/fence
triggers and limited domain privileges. Target locking lives in the SECURITY DEFINER trigger;
MCP does not gain UPDATE rights on tickets. Core execute/verify supports all three contracts.
Revision API preserves the tool type. Public arguments are operation-specific; private reads
check object access. Approval bodies/target IDs are rendered as React text, with no active HTML.

Security: SEC-01/03/06/08/10; [contracts](../../f10-security-contracts.md),
[backlog](../../../security/asvs-l2-requirement-backlog.json). Body/recipient data are tenant
confidential, recipient IDs personal. Audit/events contain identifiers/status metadata, no bodies
or JWTs. No bulk export or inbox UI is introduced. Retention/delete/export/backup and managed
storage/keys remain their explicit F17/F23 boundaries. No whole-requirement closure/N/A is inferred.
F11 DAG/approval waves and F14 complete inbox/history UI were not started.

## Measured acceptance

[checks.json](checks.json), [release log](checks.log), [image/source binding](image-source-check.json):

- Backend **331 passed / 9 dedicated skips**, on the final runtime. Ruff/format and mypy111 pass.
- All **26 F10 real PostgreSQL/MCP cases** pass (included in backend); [focused](focused.log).
- Host unit114 pass (also included); TypeScript/Vite build pass.
- Authenticated browser/OIDC **12/12**. Dedicated queue process **5**, fencing **3**:
  real kill/stop/TCP partition; [process reports](process/).
- Scripted evals **12/12**, hard safety gate true; unauthorized writes, duplicates and false
  verified success all0. [JSON](evals/scripted.json), [report](evals/scripted.md).
- Real Chromium new-body/target rendering: exact text, no active elements/XSS;
  [component result](render.json), separate from the authenticated release suite.
- Fresh native TLS/MFA lab: **8 TLS probes + 11 browser/security checks**,
  separate fresh-MFA approver, verified signed TLS action; [TLS](tls/tls-probes.json),
  [browser](tls/browser.json), [log](tls-checks.log). Final runtime was used.
- Final app/web runtime SCA has no HIGH/CRITICAL findings; exact total findings are in checks.json
  and [app](security/app-image.json)/[web](security/web-image.json) reports. Final total findings are0 for both images. Python89 distributions
  and npm audit0 findings. No threshold/assertion/deadline was weakened.
- [DB consistency/security](db-security.json), [grant/audit privilege checks](grant-security.json),
  [artifact credential check](artifact-secret-check.json).

Commands from the Full checkout:

```powershell
./scripts/test-full-f10.ps1
# optional local build-only DNS workaround, if needed:
./scripts/test-full-f10.ps1 -ComposeOverride .tools/f10-build-dns.yaml
# reuse explicitly rebuilt final images:
./scripts/test-full-f10.ps1 -SkipBuild
.venv/Scripts/python.exe -m pytest -q tests/unit
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
.venv/Scripts/mypy.exe --cache-dir .tools/f10-mypy src
# from web: npm run build; npm audit --json
# F10_CHROMIUM_EXECUTABLE may select an installed browser:
# from web: node e2e/check-f10-render.mjs
```

Release project `opspilot-full-test-f10-release`, database `opspilot_full_test`, no published ports.
Fresh hardened profile `opspilot-full-security-f10` uses a separate generated
`.tools/security-f10/compose.json` and fresh keys/passwords/CA; its credentials stay ignored.
Its invocation follows scripts/test-security-local.ps1 with that compose path/project and
`-SkipBuild -ReportDir docs/full/evidence/f10/tls`; `.tools/f10-tls.ps1` is the local wrapper.
Only report data, no secret-bearing compose/env, is committed. Source hashes are bound to the
actual tested dirty snapshot; intermediate candidate SHA is not a test of its clean parent.

## Failed candidates and remediation

Initial [engine/DNS blocker](release-blocked.log), [DNS candidate](release-dns-candidate.log),
and [first failure](release-first.log) are retained. The owner authorized Docker restart.
Graceful restart stuck in stopping, so only docker-desktop WSL was terminated before normal
startup. No reset/prune/volume deletion or change to Ubuntu was performed. Other previously
running apps recovered automatically. Build-only ignored extra_hosts used addresses resolved
by host DNS for PyPI/files/Alpine; no global DNS/MVP settings changed.

[Readiness candidate](health-pin-candidate.log) found the API schema pin still at0011; it was
updated to0012. [Comment candidate](comment-permission-candidate.log): 8 failures all traced to
SELECT FOR UPDATE requiring forbidden UPDATE privileges. The trigger already held the authorized
row lock; ordinary MCP target read was corrected, then all26 cases and full suites passed.

The initial SCA discovered eight findings (four Rustls advisories in each uv/uvx binary,
MEDIUM/LOW). [Original report](security/app-image-with-build-tool.json) is preserved. Dockerfile
separates build/test tooling from the runtime target and uninstalls unused uv/uvx there;
[runtime absence check](runtime-tools.json). Application Python dependencies are unchanged.
All release gates were repeated on the final runtime. Build/test helper tooling remains separate
from deployed application images; full toolchain/deployment acceptance remains SEC-10/F17/F23.

A diagnostic command displayed the previous synthetic TLS-lab config. It was not copied into
artifacts; the credential-value probe confirms no raw Full/lab credentials in changed artifacts.
F10 acceptance used a separate fresh synthetic lab and never reused that previous lab profile.
No Full/MVP credentials or private keys were printed or committed.

## Live rollout and preservation

Full dev upgrade0011→0012 preserves prior tickets/receipts: [upgrade](upgrade.json).
Two workers healthy, UI8091/API8011 HTTP200, SDK13 tools, real read-only queued run with
consistent events/audit: [live](live.json), [readiness](restored-full.json).
The live probe is scripts/smoke-full-f10.py, mounted read-only into the ordinary Full api container. Its initial catalog probe used to_regclass through the Core role without domain USAGE; [failed probe](dev-probe-candidate.log) is retained. The probe now reads pg_catalog directly, without expanding Core permissions.

MVP [before](mvp-before.json), [after authorized restart](mvp-after-restart.json), and
[final preservation](mvp-isolation.json): all184 source/media/docs/env fingerprints, main/HEAD,
image tags and volume metadata/read-only content match the saved baseline. The original checkout
is clean. The F01 baseline timing limitation remains explicit in the preservation report.
MVP was not built, migrated or intentionally started. Full remains on its own ports/resources.

[Cleanup](cleanup.json): F10 test/lab containers and networks removed, volumes/images retained.
Application calls only local synthetic OIDC/PostgreSQL/MCP. Dependency/scanner downloads occurred;
paid models, vendor writes, remote CI, production deployment and push were not used or claimed.

Blockers F10: none. Local stage commit subject:
`feat(full-f10): implement local ticket comment and internal inbox operations`.

Log artifacts normalize trailing whitespace for git diff checks; original command output remains in ignored .tools logs.
