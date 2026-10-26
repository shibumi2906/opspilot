# F05 — PostgreSQL commands and independent worker

The Full API commits start/resume commands and returns without scheduling graph work. A new run
and its start job share one transaction. A decision, run status change and resume job share one
transaction. Queue inserts never commit independently. Identical create/decision replay returns the
saved run; unique (tenant_id, run_id, kind) prevents a second command for the F05 single-action flow.
Conflicting decisions and changed create input retain the existing 409 behavior.

Schema 0006_command_jobs creates workflow.command_jobs (the specification's run-jobs responsibility):
tenant/run/action composite foreign keys, default-deny FORCE RLS, command kind, pending/running/done/
dead states, attempts, available_at, created_at, finished_at and redacted error_code. The workflow role
has SELECT/INSERT/UPDATE only. Claim uses a committed UPDATE with FOR UPDATE SKIP LOCKED; no network
work occurs in the queue transaction. Start mode/scenario/clock and initial model/budget definition
are persisted on the run. The initial command definition in usage is replaced by actual budget usage
when execution publishes progress. HTTP responses expose only the existing public usage DTO.

Run `python -m opspilot.runtime.worker` in the separate worker service. It owns PostgreSQL session
advisory lock 1801202605 for its lifetime; a second real worker refuses startup. API no longer owns a
singleton, scans recovery candidates or holds asyncio background tasks. The worker traverses the
configured trusted synthetic tenant catalog; each claim is tenant-filtered under RLS, and execution
loads the saved operator and current membership before checkpoint/MCP access. The approver's HTTP
context is never used as execution identity.

A failed command dispatch is retried with 2^attempt seconds, capped at 60 seconds, with five attempts
before dead-letter. Restart under the singleton treats an interrupted running claim as a failed
attempt, including backoff/dead-letter; it never resets attempts. Exhaustion atomically marks an
unfinished run failed with COMMAND_DEAD_LETTER. Raw exception strings are not stored. A graph's
explicit terminal failure is terminal, rather than automatically replaying its side effects.

Checkpoint recovery remains conservative: a saved approval interrupt can be resumed; a committed
local operation is recovered/read-verified, rather than blindly written again. An interrupted
investigation without a safe saved recovery point fails with RESTART_INTERRUPTED. Terminal runs are
not re-executed when a delivery was completed before the job acknowledgement. SIGTERM/SIGINT stops
new claims and drains the active command before releasing ownership. Compose allows 180 seconds;
SIGKILL leaves a running job for the next singleton owner.

## Local operation

From the canonical Full worktree, with its independent .env and key ring:

```powershell
docker compose -p opspilot-full -f compose.full.yaml stop api mcp worker web
docker compose -p opspilot-full -f compose.full.yaml run --rm admin
docker compose -p opspilot-full -f compose.full.yaml up -d --wait postgres oidc collector jaeger mcp api worker web
powershell -NoProfile -File scripts/test-full-f05.ps1
```

The stage gate keeps the Compose worker stopped during backend fault injection; tests explicitly
consume committed jobs in a test-only harness. Browser checks use the independent Compose worker.
The dedicated fault gate starts real API/worker processes, kills API after commit before response,
replays commands with the worker offline, kills a claimed worker, rejects a second worker, then drains
an active resume under SIGTERM and verifies one actual local ticket. The eval/CLI tools explicitly
consume persisted resume commands in their isolated execution process; they must not run against an
active production worker. They are not HTTP request schedulers. Historical API graph crash tests now
forward to the durable process gate; the current CI entry point is scripts/test-full-f05.ps1.

## Limits and scope

Exactly one worker is supported. SKIP LOCKED and a session singleton do not supply ownership epochs,
leases, stale-writer fencing or network-partition safety. Those checks and two-worker Compose belong
to F06. Transactional event/audit/outbox work belongs to F07. No new clarification, cancellation,
approval revision, connector, Redis, deployment or release-acceptance feature is included.

Dead-letter rows remain for operator inspection. There is no automatic manual-redrive API; investigate
before any retry. Tenant catalog expansion/admin tooling remains later work. All F05 checks use local
synthetic fixtures; paid provider calls and external Jira/Prometheus writes are zero.
