# F06 — ownership, epochs and fenced persistence

Full supports two independent worker services, worker and worker2. API still only commits commands.
The ownership key is (tenant_id, run_id), not a process singleton or an asyncio lock. Schema head is
0007_execution_fences; workflow version full-graph-v1 and public/checkpoint state schema 1 are pinned
on each run. The supported graph/policy topology is unchanged from F05. A different workflow/schema
or a malformed checkpoint is held in needs_attention without dispatching new writes.

## Ownership and commands

workflow.run_execution_leases has tenant FORCE RLS, a composite run foreign key, owner UUID, monotonic
epoch and lease_until. Defaults are a 30-second lease and 10-second heartbeat. Normal browser workers use the same defaults. Only explicitly selected fault subprocesses
use 3 seconds/1 second to exercise expiry on the same database-clock path. Configuration rejects
non-positive durations or heartbeat >= lease. Neither API nor the browser chooses an owner or epoch.

Claim selects an available command whose run has no live lease, then atomically acquires the run row
and records claim_owner/claim_epoch on the job. It takes ownership before mutating the command, so
claims, reaper and operation transactions share the ownership-first lock order. Competing workers
may see the same pending job; only one can acquire its run. A second command for that run waits until
the first command relinquishes ownership. Heartbeat extends only the same unexpired owner/epoch,
using clock_timestamp() in PostgreSQL. Expired ownership cannot be revived by a late heartbeat. Heartbeat first locks the row and only
then evaluates expiry; waiting for a previous transaction cannot revive an already expired lease.

Each worker reaps expired rows with FOR UPDATE SKIP LOCKED. Reaper increments epoch before resetting
the old claim, preserves attempts, uses bounded exponential backoff and dead-letters after five
failures. Exhaustion becomes needs_attention. Reaper's state change is fenced in the same transaction.
Finishing a job requires both a live ownership fence and matching job claim owner/epoch. Release
cannot erase a running claim on cancellation: that claim remains recoverable by the expiry/reaper
path. Success/retry acknowledgement permits release. No process-wide advisory singleton remains.

## Transaction contract

workflow.check_fence(run) locks the ownership row FOR UPDATE and checks tenant, run, owner, epoch and
live lease against the database clock. Missing ownership is rejected. Transaction-local execution
GUCs come from a trusted immutable ContextVar; every SQLAlchemy transaction resets them. Engine pool
reuse cannot retain a previous execution's authority. Runtime roles are not table owners/BYPASSRLS.
The narrow SECURITY DEFINER helper fixes search_path and filters the current tenant explicitly;
domain/checkpoint roles get EXECUTE/SELECT, never UPDATE ownership privileges.

Database triggers apply this check to actual writes of agent_runs projections, actions, worker
approval creation/changes, domain ticket effects/receipts, checkpoint rows, blobs and pending writes.
The API's authenticated human approval update and its exact waiting_for_approval -> running status
transition remain command ingestion and share a transaction with enqueue. Those API exceptions do
not allow snapshot/budget/outcome/error changes. Admin-only seed/migration operations have an
explicit session_user exception; worker credentials cannot become that administrative session.

The checkpoint adapter binds its fence once when constructed. It overrides the pinned SDK's cursor
boundary with a connection transaction under the saver lock. aput holds the ownership row while
writing all blobs plus the checkpoint; aput_writes holds it for every pending write in that batch.
No pipeline/autocommit gap exists between the check and data writes. The dedicated non-pooled SDK
connection binds execution session settings once; each write transaction still checks/locks the row.
Runtime workflow/domain/checkpoint connections have 5-second statement and idle-in-transaction
timeouts, so SIGSTOP while holding the SDK row lock cannot prevent takeover indefinitely. Migration
connections are exempt. Storage faults go through bounded job retry; validation/auth/policy errors
remain terminal or needs_attention. Triggers also protect raw SQL
against the same stale context. SDK write calls without an execution fence fail. Thread lookup uses
the persisted tenant/thread -> run mapping, including non-UUID compatibility probe threads.

Pre-dispatch checks stop new read/model attempts before the next heartbeat notices expiry. A lost
heartbeat/partition cancels execution. A callback that ignores cancellation still cannot persist
anything or reserve a write with the expired epoch. The fence row serializes accepted short local
transactions against takeover; there is no network call while holding it in production.

## MCP and local effects

Signed action context additionally carries execution_owner and execution_epoch. MCP validates their
shape and independently checks current DB ownership. A correct persisted approval and a valid
signature alone cannot reserve a new write. The ownership check, action lock, current membership
checks, local ticket insert and action receipt share one transaction. Concurrent deliveries reuse
one committed receipt. A missing/old/expired fence returns a redacted non-retryable STATE_CONFLICT.
Read contexts do not acquire action authority. Read/reconciliation remains available through existing
authorized read tools under a new owner's execution context.

## Recovery and operation

Queued runs survive worker loss before graph invoke. A pinned checkpoint can continue read/model
work, restore the saved budget and reuse persisted completed state. Human interrupts, committed
decisions and committed local writes retain their existing receipt-based recovery. Invalid or
unsupported state is needs_attention; recovery never silently reinterprets a future workflow or
blindly resends an unresolved effect. SIGTERM/SIGINT drains the current command and stops claiming.
SIGKILL/SIGSTOP/network partition relies on lease expiry and the reaper, not startup-wide resets.

From the canonical Full worktree only:

```powershell
docker compose -p opspilot-full -f compose.full.yaml stop api worker worker2 mcp web
docker compose -p opspilot-full -f compose.full.yaml run --rm admin
docker compose -p opspilot-full -f compose.full.yaml up -d --wait postgres oidc collector jaeger mcp api worker worker2 web
powershell -NoProfile -File scripts/test-full-f06.ps1 -Project opspilot-full-test-f06-final
```

Use the existing independently generated Full .env and service key ring. No MVP path or volume is
mounted. CLI/eval execution now acquires the same per-run ownership; SDK compatibility fixtures
also request explicit ownership. Current CI uses the F06 gate. F01-F05 reports remain historical.

## Verification and scope

The SDK fault test injects failure after blob insert and in the second pending write; all prior rows
in the failed SDK operation roll back. Two real workers contend for one run in each SIGKILL,
SIGSTOP/SIGCONT and TCP-partition case. After expiry/takeover, a deliberately late old callback tries
projection/action/approval, checkpoint, pending-write, read/model dispatch and signed MCP operation
boundaries. PostgreSQL/MCP reject the old epoch and exactly one local ticket remains verified.

This stage does not create F07 transactional run_events/audit/outbox. The current timeline is part of
the fenced public projection; future F07 event writes must use the same transaction helper. External
connector reconciliation, Redis/cost accounting, release deployment and full fault/load/soak matrix
remain their own stages. Local tests use synthetic OIDC/PostgreSQL/MCP and scripted models only.
