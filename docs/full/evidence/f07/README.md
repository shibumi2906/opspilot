# F07: persisted events, audit and projections

All changes belong to the canonical Full worktree on `codex/opspilot-full`.
MVP preservation reports are stored alongside this file. No MVP migration, build or runtime reset is part of F07.

## Transaction and ownership boundaries

Migration `0008_transactional_events` adds tenant-scoped, FORCE-RLS `run_streams`,
`run_events`, `run_audit`, `event_outbox` and `event_delivery`. Runtime roles have
SELECT only on this storage. Fixed-search-path SECURITY DEFINER triggers append an
allowlisted event, an audit entry and an outbox row in the exact transaction that
creates/updates a run, approval or action receipt. Failure of any insert rolls the
state change back. Operation events commit with the existing local ticket and receipt.
F06 ownership checks still run before state mutation. Recovery recording itself
requires a current fence. Existing runs receive an explicitly labelled `run.baseline`;
the migration does not invent missing historical decisions.

A per-run stream row serializes sequence allocation. Event IDs are stable UUIDs;
`(tenant_id, run_id, sequence)` is unique. Events carry schema version 1, timestamp,
snapshot version and at most 4096 bytes of public metadata. Payloads contain status,
outcome, action IDs and decisions or safe reason codes. They never contain request
text, graph state, observations, tool arguments/results, credentials or exception text.
Audit links the same event/sequence/run with actor, database service identity, action,
execution epoch, reason code and a redacted changed-value diff.

## Replay, delivery and snapshot recovery

The worker drains at most 100 pending outbox records per tenant iteration. Publication
updates the delivered watermark and sends PostgreSQL NOTIFY in one transaction.
Wakeups carry run ID and sequence only. A crash before this commit leaves the row
pending; duplicates are allowed and `GREATEST` prevents out-of-order delivery from
moving the watermark backwards. Delivery never writes run state or projections.
There is no event transport dependency for authorized DB replay.

`GET /api/v2/runs/{run_id}/events` and `/audit` use existing object authorization
before reading cursor or replay data. Signed cursors bind actor, tenant, run, stream,
version and sequence. Pages contain 1–100 records within the latest 1000 committed
sequences. An older/future cursor returns `reset_required`, the earliest available
sequence and current snapshot version. Clients can fetch the snapshot and restart.
Storage retention/archival belongs to F17; the bounded public replay window does
not delete append-only audit. SSE and Last-Event-ID remain F13.

The stream retains the authoritative committed graph projection independently of
the legacy `agent_runs.public_snapshot` cache. Snapshot reads use a repeatable-read
transaction and rebuild the view from that source plus current run, action, approval
and operation receipt rows. Erasing the legacy cache cannot erase the report or
receipt. New graph projections update their source and version transactionally;
wakeups are never applied as state patches. The public snapshot is exported through
an explicit nested allowlist, DTO version 1 and snapshot version. Internal graph
keys, budgets, raw observations and trace carriers are excluded. Public normalized
evidence excerpts and explicitly allowlisted tool facts remain available. Membership mutation and its existing
security audit now share the same transaction.

## Verification

Release command: `powershell -NoProfile -File scripts/test-full-f07.ps1`.
Isolated project `opspilot-full-test-f07`, database `opspilot_full_test`; test ports
are removed. Checks include Ruff/format/mypy, backend DB/API tests, real OIDC browser
flows with two workers, inherited queue/fencing subprocess faults and 12 scripted
evals. Dedicated accelerated fault timing remains 3/1 seconds; ordinary runtime
uses the production 30/10 seconds. Measured results: **222 passed, 9 skipped**; all **11 F07 cases** passed.
Ruff/format passed (148 files), mypy passed (100 source files). Browser **12/12**;
queue process suite **5 passed** (four repeated main cases + one additional case);
fenced multiworker subprocess suite **3 passed**. Total **226 unique backend cases**.
Scripted regression **12/12**, hard safety gate true. [Measured counts](checks.json),
[eval report](evals/scripted.md), [SIGKILL](process/kill.json),
[SIGSTOP](process/stop.json), [TCP partition](process/partition.json).

New tests cover transactional rollback before/after event inserts, create replay,
12 concurrent independent sequence allocations, real process exit after commit
before publication, duplicate/out-of-order delivery, projection restoration from
source/receipt, recovery/create/approval/operation audit, runtime append-only grants,
private-state redaction, tenant RLS and cursor actor/tenant/run/stream binding,
1000-event window reset and stale-epoch recording rejection.


The first backend candidate exposed one missing public client_request_id and two test
assumptions that a bounded publisher batch drains the whole database. These were fixed
and the complete backend suite rerun successfully. The first browser run had two worker
connection/timeouts while both dev Full and the test stack were running; after stopping
only dev Full, the complete 12-case browser suite passed. No timeout limit was increased and no
runtime logic was changed to obtain that result. Final line-wrap-only changes to three
source files were checked for AST identity with the tested image, then linted/formatted.

Reproduction entry point remains scripts/test-full-f07.ps1. The measured successful
backend gate is in ignored .tools/f07-final-checks.log. After the resource-related browser
failure, only browser and the remaining gates were rerun: .tools/f07-remaining.ps1/log
contains the same Compose commands from worker startup through browser, queue, fencing,
stop. The fault assertions initially reached report writing but the new process output
directory was absent. The release script now creates both report directories; the three
fault cases and evals were rerun in .tools/f07-faults.ps1/log. No backend failure is counted as a pass; no remote CI run is claimed.
Fresh test installation reached 0008; dev Full was separately upgraded from 0007, with
historical runs receiving baseline events. Final dev Full has both workers running,
UI 8091/API 8011 HTTP 200, nine scoped MCP tools (protocol 2025-11-25), and a new synthetic
diagnosis run completed with matching persisted event/audit counts and zero pending
outbox rows. [Live evidence](live.json). The live replay probe calls the authorized
repository route internally; HTTP session/OIDC coverage is provided by the browser suite.
Test services were stopped without removing volumes.

MVP: 184 source/media/docs/.env fingerprints, branch/head, four image tags and volume
metadata/content match both before and after rollout: [before](mvp-before.json),
[after](mvp-isolation.json). The original checkout remains clean. Existing F01 baseline
volume timing limitations remain explicit in the preservation reports. Provider/vendor
calls: zero; all application calls use local synthetic OIDC/PostgreSQL/MCP.
F08 has not been started. Commit subject: feat(full): implement F07 transactional events audit and projections.
