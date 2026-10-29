# F12 — freshness, expiry, revocation and bounded replan

Status: **done**, 29 October 2026. Base F11 `4d70288`; only F12 completed.
Schema `0014_freshness`, existing pinned v1/v2 graphs/checkpoints retained, DTO/schema1 and SDK9.
Complete ASVS L2 remains **NOT_MET**; F13–F24 remain not_started.

## Result

- Each new revision binds fresh bounded local configuration/monitoring preconditions. Core reads
  directly before dispatch and grant issuance; MCP independently checks inside its effect transaction.
  Monitoring checked_at must be within5 minutes of DB time and cannot be future; the local synthetic
  adapter uses DB observation time for its direct read. Source timestamps are validated, not restamped.
  Configuration/target rows use share locks; checkpoint/cache observations never authorize a write.
- Same conditions permit dispatch. Healthy means no longer required; unknown/timeout/disabled target
  never satisfy conditions. Explicit unavailable previews cannot receive a grant. Public cards expose
  bounded status/IDs/role eligibility and configuration/project fingerprints, not raw configuration.
- Material drift supersedes an unexecuted revision and revokes its grants. One new immutable revision
  requires a distinct saved decision, preserving stable logical intent and completed sibling receipts.
- At most1 replan/run and2 approval rounds. Single/one-wave plans can spend their second round on a
  replacement. In a DAG already reserving2 dependency waves, a changed intent stops; no third round is allocated.
  Both Core and the SQL slot pointer guard enforce this. No completed/uncertain intent is replanned.
- DB clock governs expiry; retained bounded worker sweeps and decisions serialize on existing locks.
  Current actor/approver roles, self-approval policy, cancellation, TTL and exact revisions are checked
  independently again at MCP. Active legacy waiting approved runs remain valid; terminal runs cannot
  issue new effects. Existing succeeded receipts remain available through authorized reconciliation.
- A separate persisted verification quota (3/action), FORCE RLS and execution fencing survive restart.
  Existing mixed-slot verification reserves remain separate from research. No uncertain write retry.
- A real child worker exits99 after replacement commit but before checkpoint. Recovery restores the
  new pending approval and needs a new decision; it does not execute with old consent.

[Security contracts](../../f12-security-contracts.md),
[scoped ASVS review](../../../security/asvs-l2-requirement-backlog.json).
This is the existing local synthetic monitoring adapter and local effects. No production connector,
Redis authority, managed keys, external project writes, real provider evaluation or F13 SSE is claimed.
Legacy missing snapshots need replacement consent if round budget permits, otherwise fail closed.

## Measured acceptance

[checks.json](checks.json), [complete release log](checks.log), [source/image match](image-source-check.json).

| Gate | Result |
| --- | --- |
| Complete backend | 368 passed /9 dedicated skips; includes15 F12 and26 F10 MCP cases |
| Host unit | 126 passed, subset of backend |
| Real OIDC/browser | 15/15, including bound replacement revision/new decision |
| Queue process | 5 passed |
| Fencing kill/stop/partition | 3 passed |
| Native TLS/MFA | 8 probes +11 browser checks |
| Scripted eval | 12/12, hard safety gate true; unauthorized/duplicate/false verified0 |
| Ruff/format/mypy | pass,117 application files |
| TypeScript/Vite | pass |
| Runtime app/web HIGH/CRITICAL SCA | 0 findings |
| Runtime Python/npm package audits | 0 findings |

F12 covers DB TTL boundary and skewed observation clock, old cached observations vs fresh healthy/
unknown/timeout/stale/future source timestamp, changed project and recipient, replan cap and third-wave denial, role revocation after
signed grant, independent MCP denial after grant/config race, separate verification quota, real crash
between replacement and checkpoint, and preservation of a completed sibling. Existing grant current/
next overlap, key retirement, expiry/revoke races and fresh-MFA regression tests pass unchanged.

[DB/security](db-security.json), [grant/audit](grant-security.json), [unit](unit.log), [46-case focused gate](focused.log),
[types](types.log), [lint](lint.log), [recipient](recipient.log), [build](web-build.log),
[process faults](process/), [TLS probes](tls/tls-probes.json), [TLS/MFA browser](tls/browser.json),
[TLS log](tls-checks.log), [eval JSON](evals/scripted.json), [eval report](evals/scripted.md),
[app SCA](security/app-image.json), [web SCA](security/web-image.json),
[Python audit](security/python-audit.json), [npm audit](security/npm-audit.json).

Reproduce from Full:

```powershell
./scripts/test-full-f12.ps1
# canonical isolated project: opspilot-full-test-f12-acceptance; no published ports
./scripts/test-full-f12.ps1 -SkipBuild
.venv/Scripts/python.exe -m pytest -q tests/unit
.venv/Scripts/ruff.exe check src tests scripts/check-f12-security-state.py scripts/smoke-full-f12.py
.venv/Scripts/ruff.exe format --check src tests scripts/check-f12-security-state.py scripts/smoke-full-f12.py
.venv/Scripts/mypy.exe --cache-dir .tools/f12-mypy src
```

Fresh TLS profile opspilot-full-security-f12-final uses separate generated ignored credentials/CA.
Local wrapper .tools/f12-tls-final.ps1 follows scripts/test-security-local.ps1 with that compose/project
and -ReportDir docs/full/evidence/f12/tls. Lab directory traversal was corrected for the probe's CA
mount; credential files and validation were unchanged. No secret-bearing env/compose is committed.

## Failed candidates and limits

[Initial](initial-candidate.log): replan/checkpoint lock inversion, missing typed MCP freshness error
and pending-wave denial assertion. Lease-first lock order and typed errors fixed; no fence weakened.
[Crash timing](crash-timing-candidate.log): test resumed before reaper backoff; bounded15s polling now
uses actual durable recovery, same as existing F11 process checks.
[Target error](target-error-candidate.log): early grant denial obscured existing authorized NOT_FOUND
semantics. MCP independently checks permitted target before consume, still inserts only after every
authorization/freshness gate. Original F10 assertions were retained.
[Usage counter](usage-counter-candidate.log): separate verification quota initially omitted1 read from the
legacy diagnostic total; projection now reports total/research/verification separately without changing
quota authority. [Metrics regression](metrics.log) and full368 pass.
[Recipient fixture](recipient-fixture-candidate.log): a previous test left a disabled member; new
recipient fixture explicitly chooses an enabled member. Assertions and write expectations unchanged.
[TLS permission](tls-permission-candidate.log): initial lab CA mount traversal error, corrected locally.
Final full368 run supersedes candidate results; none of these red runs are presented as final success.

## Live and preservation

[Upgrade](upgrade.json): Full013→014 preserved counts and SHA256 of existing domain objects/actions/
receipts. [Live v1/v2](live.json): read-only v1 and normal mixed v2,2 approval waves,3 verified receipts,
request replay returns same run, MCP13 tools. Live probe covers compatibility; drift/crash cases are
in isolated real PostgreSQL/MCP tests. [Readiness](restored-full.json): UI8091/API8011 HTTP200,2 workers.

MVP [before](mvp-before.json) and [final](mvp-isolation.json):184 source/media/docs/env fingerprints,
main/HEAD, image tags, volume metadata and read-only content match baseline. Original checkout clean.
Initial F01 volume-baseline timing limitation remains explicit in preservation evidence.
[Cleanup](cleanup.json): only F12 test/lab containers/networks removed; volumes/images retained.
No Docker restart/prune/volume deletion. Dev Full remains running. Paid/vendor writes, remote CI,
production deployment and push0. Application calls are local synthetic OIDC/PostgreSQL/MCP;
dependency/scanner downloads occurred.

[source-tree.json](source-tree.json) binds the actual tested dirty worktree; all117 installed app
files match source. Evals name the dirty parent, not a claim of testing its clean commit.
[Image IDs](images.json), [credential artifact check](artifact-secret-check.json).
Logs normalize trailing whitespace; ignored .tools retains raw output.
All253 ASVS IDs/levels/baseline assessments/owners preserved. Scoped SEC-02/03/04 and SEC-01/10
change gates pass; whole-norm/production L2 acceptance remains NOT_MET. F13 not started.

Blockers F12: none. Local stage commit subject:
`feat(full-f12): enforce freshness and bounded reapproval`.
