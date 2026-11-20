# Full architecture baseline (F01)

F01 isolates the inherited application; it does not claim Full Core authorization or workers exist.
Application baseline: `01019b69dbf0b300d2ab2a600089f19a638d2108`.
Planning base: `f9f8d79`. Canonical tracker: [../full-version-status.md](../full-version-status.md).
MVP remains in its original checkout, branch, config and Docker project.

## Boundaries

Browser → API → deterministic core/LangGraph → authenticated private MCP → domain DB.
The model selects bounded reads and proposes typed writes; core owns policy, approval and verification.
PostgreSQL owns workflow/domain/receipts/checkpoints; MCP owns transactional domain effects.
The existing F01 runtime still runs orchestration in API with one ticket action and service-token MCP.
F02–F04 add tenancy/OIDC/authorization; F05–F07 separate workers and durable fenced ownership/events.
F08–F17 extend the local Core; F18–F24 add adapters and actual pilot acceptance.
No new migration, tenant table, OIDC service or worker is introduced by F01.

## Resources

Full Compose is standalone: `compose.full.yaml`, project `opspilot-full`, DB `opspilot_full`,
volume `opspilot-full_pgdata`; tests use `compose.full.test.yaml`, project `opspilot-full-test`,
DB `opspilot_full_test`, volume `opspilot-full-test_pgdata`. App images use `opspilot-full/*`.
Postgres/collector/Jaeger use own opspilot-full/* tags built FROM pinned upstream digests; immutable layers may be shared. MVP image tags never move.
No Full service mounts MVP source, media, env or volumes. DB/MCP are private to each project network.
Full public ports: UI 8091, API 8011 (8010 occupied), Jaeger 16696; 8181 reserved for F03 OIDC.
Independent randomly generated local secrets are ignored by Git. No MVP credentials are copied.

## Setup and checks

From this Full worktree, run `powershell -File scripts/new-full-env.ps1` once.
It refuses to overwrite .env and checks prospective public ports. Adjust only the Full template if busy.
Then `docker compose -p opspilot-full -f compose.full.yaml up -d --build --wait postgres`,
`docker compose -p opspilot-full -f compose.full.yaml run --rm admin`,
`docker compose -p opspilot-full -f compose.full.yaml run --rm admin python -m opspilot.cli.seed`,
and `docker compose -p opspilot-full -f compose.full.yaml up -d --build --wait mcp api worker web`.
Use `powershell -File scripts/test-full-f01.ps1` for lint/types/backend/browser/recovery/12 scripted evals.
Tests stop only their project and preserve its volume. No paid provider requests are part of F01.
Both URL and server database identity are checked before domain/application SQL; migration uses the same guard.
Tests/evals only accept opspilot_full_test; neither MVP DB name is allowed by Full engine.
Legacy Compose filenames and stage test scripts in this checkout also address Full resources.

## Preservation evidence

Local ignored `.tools/mvp-before.json` captures all tracked MVP file hashes, .env hash, branch/head,
MVP image IDs, volume metadata and container inventory before any Full build/migration.
The MVP `.tools/opspilot-full-workspace.json` is the only local pointer added there (ignored).
Final evidence compares file fingerprints and Docker resources; existing MVP containers are never started.

## F02 update

Tenant foundation is now implemented; see [tenancy.md](tenancy.md) and
[ADR 004](adr/004-tenant-isolation.md). Schema head is 0003_tenant_rls, runtime checkpoint DDL is now
administrative. Use scripts/test-full-f02.ps1 for the current stage gate; its regression portion reuses
the F01 script. F02 reports go to evidence/f02/evals, preserving evidence/evals as the F01 baseline.
OIDC and public multi-user authorization remain unimplemented F03/F04 work.

## F04 current boundary

F04 supersedes the fixed local MCP scope/V1 baseline described above. Authenticated V2 and signed
per-actor/tenant/run MCP context are implemented; see [authorization.md](authorization.md).
API background execution is still not F05 durable workers; F06 fencing remains future work.

## F05 update

Full API now commits durable start/resume jobs; the separate single worker owns graph execution.
Schema head 0006_command_jobs. See [durable-jobs.md](durable-jobs.md) for queue semantics, recovery,
shutdown and the exact F06 boundary. Current gate: scripts/test-full-f05.ps1. Previous stage text above
records the historical baseline; canonical progress is docs/full-version-status.md.

## F06 current boundary

Two independent workers use DB-clock per-run ownership epochs, heartbeat/reaper and transactional
fencing for snapshots, local operations and SDK checkpoint/pending writes. Schema 0007_execution_fences;
workflow full-graph-v1, public state 1. See [execution-fencing.md](execution-fencing.md) and
[ADR 006](adr/006-fenced-checkpoint-adapter.md). Current gate: scripts/test-full-f06.ps1. F07 events/outbox
are not implemented by this stage; earlier stage sections record their historical boundary.


## F07 current boundary

Schema head is `0008_transactional_events`. Run/action/approval state transitions append
versioned public events, append-only audit and outbox in the same DB transaction.
Per-run stream locking allocates monotonic sequences. Two workers publish bounded batches
of identifier-only PostgreSQL wakeups; repeated/out-of-order delivery cannot change state.
Authorized event/audit replay has signed scope-bound cursors, at most 100 items per page
and a 1000-sequence public window with snapshot reset. Snapshots read the committed source
projection and authoritative run/approval/receipt rows under repeatable read, then export
through the public DTO allowlist (version 1). See [F07 evidence/contract](evidence/f07/README.md).
Current gate: `scripts/test-full-f07.ps1`. SSE is F13; storage retention is F17.
