# F13 — authenticated SSE replay/reconnect

Status: **done**, 29 October 2026. Base F12 `abfaf76`, branch `codex/opspilot-full`, canonical Full
worktree. Only F13 completed; F14–F24 remain not_started. Full ASVS L2 remains **NOT_MET**.
Schema `0014_freshness`, pinned v1/v2 graphs, DTO/state1 and checkpoint SDK9 retained; no migration.
Graph blob `05efb29565b989d831ced8bc2acdc11750b88efb`, policy blob
`d7c0a37ffd28b02b344ce88a6c0639d4bf94b315` unchanged from F12. Cursor protocol v1.

## Result and security scope

[Contracts](../../f13-security-contracts.md). Explicit `Accept: text/event-stream` selects SSE;
F07 bounded JSON replay stays the default. A repeatable snapshot exposes snapshot_version and
signed latest_event_id; DB replay/live handoff covers events committed between snapshot and
subscription. Compacted/gapped/over-window cursors produce reset and snapshot recovery.

Cursors bind session, actor, tenant and run and travel in Last-Event-ID, with cookie authentication;
SSE rejects query parameters. Each batch/event rechecks current expiry, disable, membership,
tenant and object/role access. Only bounded public metadata is streamed. Heartbeats have no
business ID. Shared PostgreSQL reservations enforce global8/tenant4/actor2; physical lease loss
closes the stream. Batch64, lag256, frame16KiB, lease probe1s, send deadline3s; composed established
revoke bound26s before scheduling jitter. Real IdP-disable TLS SSE revocation measured **886ms**.

The browser deduplicates sequences and shares one serialized authoritative snapshot reader with
polling fallback5–10s. Snapshot publication wakes the stream before UI publication, eliminating
parallel initial reads and terminal refetches. Reset requests a fresh snapshot generation; transport
reconnect never submits a mutation. Auth loss clears private DOM; run404 retains the valid session
and shows the existing investigation-not-found view.

SEC-02/07/08 and common SEC-01/10 gates pass for this change. All253 IDs/levels/baseline assessments/
owners/statuses remain unchanged;169 scoped contributions do not close whole ASVS requirements.
[ASVS integrity](asvs-integrity.json), [acceptance](checks.json).

## Measured acceptance

| Gate | Final result |
| --- | --- |
| Full backend |382 passed /9 dedicated skips, including14 SSE cases |
| SSE + existing F07 focused |25 passed, subset of backend |
| Host unit |129 passed, subset of backend |
| Real OIDC/Chromium |17 passed, including offline/logout and duplicate/reset cases |
| Durable queue processes |5 passed |
| Fencing kill/stop/partition |3 passed |
| Native TLS + real MFA/browser |8 +13 checks; IdP-disable SSE close886ms without polling /auth/me |
| Scripted regression evals |12/12, hard safety gate true; unauthorized/duplicate/false verified writes0 |
| Ruff/format/mypy |pass,119 application files |
| TypeScript/Vite |pass; final web image tested with all17 cases |
| Runtime app/web HIGH/CRITICAL SCA |0 blocking findings |
| Python/npm package audits |0 findings |
| Live existing Full |real OIDC, diagnosis_only, header cursor, actual API restart/reconnect, logout/private DOM reset |

[Backend](backend-final.log), [browser/process/SCA/eval log](browser-process-security-eval-final.log),
[focused](focused-final.log), [unit](unit-final.log), [lint](lint.log), [types](types.log),
[process reports](process/), [TLS probes](tls/tls-probes.json), [TLS/MFA browser](tls/browser.json),
[TLS log](tls-checks.log), [eval JSON](evals/scripted.json), [eval report](evals/scripted.md),
[app SCA](security/app-image.json), [web SCA](security/web-image.json),
[Python audit](security/python-audit.json), [npm audit](security/npm-audit.json).

Backend and final119-file app image are unchanged by the later browser-only reader fix; all17
browser cases and scans use the rebuilt final web image. Evals identify dirty parent abfaf76,
not a claim of testing its clean commit. [Source](source-tree.json), [image source check](image-source-check.json),
[image IDs](images.json), [credential artifact check](artifact-secret-check.json).

## Commands and local preservation

From the canonical Full worktree with its existing isolated environment:

```powershell
./scripts/test-full-f13.ps1 -Project opspilot-full-test-f13-final
./scripts/test-full-f13-tls.ps1 -SkipBuild
./scripts/deploy-full-f13-local.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent'
# Repeat only the read-only live transport probe (restarts Full API):
node scripts/smoke-full-f13.mjs
```

The backend gate completed before a second Docker500 interrupted browser startup. The remaining
commands were resumed from worker startup (same app image) using the new private-IPC/memory-bound
`compose.full.f13-checks.yaml` runner; assertions/deadlines were retained. TLS ran afterward in
separate project opspilot-full-security-f13-final with fresh generated ignored credentials/CA.
No test ports were published. No operating-system trust-store change.

Full rollout quiesced workers and compared counts and sorted JSONB SHA256 of tickets, comments,
notifications, actions and successful receipts before/after API/MCP/web restart; schema stayed0014.
[Preservation](rollout-preservation.json). Read-only live run, real API restart/reconnect and logout
passed ([live JSON](live-sse.json), [live log](live-final.log)). UI8091/API8011 HTTP200 and two workers
healthy ([readiness](restored-full.json)). No existing domain object/action changed during rollout.

MVP [before](mvp-before.json), [after restart](mvp-after-restart.json),
[after second restart](mvp-after-second-restart.json), [final](mvp-isolation.json):184 source/media/docs/
env fingerprints, main/HEAD, four image tags, volume metadata and read-only volume content unchanged.
Original checkout clean. The inherited F01 volume-baseline timing limitation remains explicit.
F13 test/lab containers/networks removed; volumes/images retained ([cleanup](cleanup.json)).
Development Full remains running. Application calls only local synthetic OIDC/PostgreSQL/MCP;
dependency/scanner downloads occurred. Paid/provider/vendor writes, remote CI, production deployment
and push0. The12 evals are regression fixtures, not the50-case F22 acceptance.

## Failed/interrupted candidates and resolved issues

- [Initial build/backend](interrupted-candidate.log) reached56% before Docker API500/WSL hang;
  [parallel setup](interrupted-final-setup.log) also stalled. Neither is acceptance evidence.
  Owner explicitly authorized Docker Desktop restart, including other-container interruption.
- [Collection](collection-candidate.log): unit/integration module basename collision; unit renamed
  test_sse_protocol.py. [SQL formatting](sql-format-candidate.log): long SQL string split; SQL and
  assertions unchanged.
- [JSON compatibility](replay-compatibility-candidate.log):2 F07 failures/379 passes; explicit Accept
  negotiation preserves the original bounded JSON contract. [Compatibility focus](focused-compatible.log).
- [Pre-send hardening](pre-timeout-candidate.log) and [pre-lease health](pre-lease-health-candidate.log)
  were intentionally stopped to verify final3s sends and fail-closed reservation health. Final25
  focused cases include actual pg_terminate_backend of the reservation and fresh subsequent admission.
- A second Docker500 occurred after the successful382-case backend, during runner startup. Docker
  restart hit an inaccessible stale telemetry socket. The runtime directory contained only that
  socket; it was preserved as `C:/Users/user/AppData/Local/Docker/run.f13-stale-20261029`, and a new
  empty runtime directory restored startup. Container/volume data and Docker settings were retained.
  The private IPC/heap/container bounds are test-runner isolation, not a claim about the root cause.
- [Browser candidate](browser-candidate.log):14 passed/3 failed due duplicate snapshot reads,
  terminal refetch and run404 losing the session. One serialized reader fixes all3 with unchanged
  assertions; final17 pass.
- [Live offline-emulation candidate](live-offline-emulation-candidate.log): the short Edge offline
  interval did not yield a new response, so the probe now creates an actual Full API transport
  interruption. Read-only result/rollout preservation already passed; final actual restart passes.

No F13 blockers remain. Local stage commit subject:
`feat(full-f13): add authorized bounded SSE replay and reconnect`.
