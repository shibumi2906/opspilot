# F06 evidence

Implementation: 26–27 October 2026; final gates: **27 October 2026**.
Canonical worktree: `C:/Users/user/.codex/worktrees/opspilot-full-f01/AI Incident & Operations Agent`.
Branch codex/opspilot-full; base 0f705a00fa90d342178094f50920f8fa5e60a7fe.
Commit subject: feat(full): implement F06 multiworker leases and fenced checkpoints.

## Final measured gates

Current entry point: `powershell -NoProfile -File scripts/test-full-f06.ps1`.
Default isolated project: **opspilot-full-test-f06-final**, database **opspilot_full_test**;
private volumes/networks, no public test ports. Earlier development projects were stopped without
removing volumes. Fresh schema creation to 0007 and the separate dev Full 0006→0007 upgrade were
both performed. No active MVP database was exported or migrated.

Final source was built before executing checks; no image builds ran during the successful browser
suite. Command prefix below is used throughout:

```powershell
docker compose -p opspilot-full-test-f06-final -f compose.full.yaml -f compose.full.test.yaml
```

Main stage invocation: `powershell -NoProfile -File scripts/test-full-f06.ps1 -SkipBuild`.
[Counts/versions](checks.json). Main **211 passed, 9 skipped**; Ruff and format passed; mypy passed
for **98 source files**. Nine skips: four legacy destructive fixture migrations, one legacy process
entry point, the dedicated queue process case and three dedicated F06 process cases. The inherited
three checkpoint recovery cases are included in 211, not an extra denominator.

The actual SDK fault test injects failure after blob insert/before the checkpoint row and in the
second pending write; all earlier writes in the failed SDK transaction roll back. Main tests also
prove missing-context tenant deny, pinned workflow/schema rejection, corrupted checkpoint binding
holding needs_attention with zero ticket dispatch, heartbeat blocked past expiry cannot renew, and
old epoch is rejected even when the new owner reuses exactly the same UUID.

Real OIDC/browser suite with **both Compose workers**: **12 passed**. Normal regression uses the
production **30-second lease / 10-second heartbeat**. Accelerated 3/1 timing belongs only to explicitly
selected fault subprocesses, including the inherited process recovery fixture.

The initial dedicated queue case found a test startup race: SIGTERM could arrive before the new
worker installed its handlers and return -15. A test-only ready marker now runs after handler
installation; production worker scheduling/authority is unchanged by this fixture. Only the affected
process gates were rerun after that fixture fix. Final commands, appended to the prefix above:

```powershell
run --rm --no-deps -e TEST_QUEUE_PROCESSES=1 -e WORKER_LEASE_SECONDS=3 -e WORKER_HEARTBEAT_SECONDS=1 tests python -m pytest -p no:cacheprovider -xq tests/integration/test_durable_jobs.py
run --rm --no-deps -e TEST_F06_PROCESSES=1 -e WORKER_LEASE_SECONDS=3 -e WORKER_HEARTBEAT_SECONDS=1 -e F06_REPORT_DIR=/reports/process -v "${PWD}/docs/full/evidence/f06:/reports" tests python -m pytest -p no:cacheprovider -xq tests/integration/test_execution_fences.py
```

Queue suite **5 passed**, four repeated main cases plus one real API commit-loss/replay/graceful-drain
case. F06 suite **3 passed**, each with two actual independent workers contending for one run:

- [SIGKILL](process/kill.json): committed claim survives; expiry/reaper/takeover resumes the queued
  run, human approval and verification complete; one ticket, epoch 1→4.
- [SIGSTOP/SIGCONT](process/stop.json): old worker holds an actual SDK transaction/ownership row lock.
  Server-side idle timeout releases that abandoned transaction; expiry/reaper permits takeover.
  A deliberately late callback ignores cancellation long enough to attempt all eight boundaries;
  every attempt is rejected, including fresh signed MCP context carrying the old epoch.
- [TCP partition](process/partition.json): a bidirectional TCP proxy cuts the old worker's workflow
  and checkpoint DB connections and rejects reconnects. The other worker connects directly, takes
  over after expiry and completes. After reconnect, the old callback is rejected at all eight
  boundaries. This is real socket failure, not a mocked database response.

Eight boundaries: projection/timeline, action, approval mutation, checkpoint, pending writes, local
operation, read dispatch and model dispatch. Ticket and pending-write/blob counts plus the final
report remain stable. Each scenario has exactly **one actual local ticket**, outcome actions_verified,
and final owner released. Total **215 unique backend cases** (211 + one queue process + three faults).

Final scripted regression command, with the same prefix:

```powershell
run --rm --no-deps evals python -m opspilot.evals.runner --mode scripted --commit 0f705a00fa90d342178094f50920f8fa5e60a7fe --dirty
stop
```

**12/12**, hard safety gate true. [JSON](evals/scripted.json), [summary](evals/scripted.md).
These inherited scripted cases do not claim F22's future 50-case/real/holdout acceptance.
Raw ignored logs: .tools/f06-timings-gate.log (main/browser), f06-queue-final.log,
f06-faults-final.log, f06-evals-final.log and f06-final-live-sdk.log. Test services stopped without
volume removal. Earlier red development runs, transient Docker EOF/DNS and an invalid test SQL probe
were not counted as passed; their corrected scenarios are covered by the final gates above.

## Live Full, isolation and scope

Schema 0007_execution_fences; workflow full-graph-v1, graph/policy blobs unchanged; public state and
signed service context version 1, SDK migration 9. Installed SDK versions are recorded in checks.json.
Only Full api/mcp/workers/web were stopped/recreated for rollout. Final live Full has two running
workers; UI 8091 and API 8011/health return 200, scoped MCP SDK negotiates 2025-11-25 and lists nine
tools. OIDC remains 8181 and Jaeger 16696. [Live runtime evidence](live.json).

MVP preservation was checked before implementation, again after resuming on 27 October and after
final rollout: [before](mvp-before.json), [resume](mvp-resume.json), [after](mvp-isolation.json).
All 184 tracked source/media/docs/.env hashes, original main/HEAD f9f8d79, four image tags, volume
metadata and read-only volume-content fingerprint match the saved baseline. The original checkout
remains clean. The F01 baseline's volume timing limitation remains explicit in the reports.

Docker Desktop could not start on resume because one stale zero-byte telemetry socket was an
inaccessible Windows reparse point. Only the verified runtime directory containing that socket was
renamed to a recovery backup, then Desktop started. No factory reset, Docker settings change or
volume deletion was used. No MVP service was intentionally started, migrated or built.

[Runbook](../../execution-fencing.md), [ADR 006](../../adr/006-fenced-checkpoint-adapter.md).
F07 events/audit/outbox are not implemented here; the existing timeline is part of the fenced
projection. No connector, load/soak, paid model, remote CI or pilot deployment is claimed. Application
calls were local synthetic OIDC/PostgreSQL/MCP; paid provider/vendor calls **0**. F06 blockers: none.
Next F07 remains not_started.
