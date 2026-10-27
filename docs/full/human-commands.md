# F08 — durable clarification and cancellation

API commands require an active operator membership and ownership of the run. Tenant scope
comes from the authenticated session. Both endpoints use the existing session/CSRF gate.

- `POST /api/v2/runs/{id}/clarifications`: `clarification_id`, `expected_version` (1–2),
  `kind` (`customer`, `integration`, `timezone`), `choice`, `command_id`.
- `POST /api/v2/runs/{id}/cancel`: `command_id`.

Answers must select an exact identifier from the persisted allowlist. A stale, expired,
forged or opposite answer returns 409. Replay of the exact committed command is harmless,
including after the next clarification round. A reused command key with different input
returns 409. Run row, human command, event/audit/outbox and resume job commit together.
Runtime roles cannot update or delete the human-command ledger. Tenant RLS applies to it.

Preparation precedes the pure LangGraph interrupt node. The checkpoint contains the typed
form, stable UUID derived from run/round, options and expiry. The run row is the API projection;
recovery repairs a next-round checkpoint whose projection did not commit yet. The worker
resumes only with the persisted answer, never an untrusted resume payload. There are at most
two rounds. Missing candidates or exhausted rounds produce insufficient_context. The first
TTL is 24 hours, configurable with CLARIFICATION_TTL_SECONDS. API acceptance uses DB time;
an answer accepted within TTL survives queue delay. Expiry sweeps enqueue bounded batches
of 100; they do not invoke the graph in the API. Human wait is excluded from the restored
active-processing budget. No model/read/write dispatch happens while waiting for input.

Customer ambiguity and multiple integrations require explicit selection. The tenant/demo
profile supplies the normal timezone; an explicit timezone question offers that zone and UTC.
Classification receives the selected timezone. The synthetic provider uses IANA ZoneInfo,
including the different UTC offsets at local midnight across the Jerusalem DST transition.
The general clarification UI belongs to F14; the F08 interface is the authorized API/DTO.

Cancellation records `cancelling` plus a durable cancel command. The worker checks the flag
before each graph node and model/read dispatch. MCP checks cancellation again in the local
write transaction. Cancel and local write acquire the same ownership-row lock first: a write
that committed first remains recorded, and cancellation accepted first prohibits a new write.
A completed receipt may still be replayed as evidence; it does not authorize another write.
The worker builds a cancelled report from committed action receipts, listing effects,
unknown/failed outcomes and undispatched cancelled actions. It preserves completed effects
and never claims that cancellation undid them. A DB trigger keeps a cancelling run from
being transiently committed as completed by an in-flight worker projection.

States added in F08 follow the Full contract: waiting_for_input → queued, and active/waiting
states → cancelling → cancelled. Inherited F05 approval resume still uses its existing
waiting_for_approval → running path; approval revisions/TTL are F09. Workflow full-graph-v1,
state/DTO/event schema 1 and checkpoint SDK migration 9 remain compatible with already saved
F07 approval interrupts. The new clarification keys and graph node are additive; no old pending
approval node is renamed. Database migration is 0009_human_commands.

Reproduce with `powershell -NoProfile -File scripts/test-full-f08.ps1`, isolated Compose
project opspilot-full-test-f08-release, database opspilot_full_test. No MVP resources are used.


F09 уточнение: все decision requests теперь обязаны передавать strict expected_version
из текущей snapshot.action. Revisions и revoke описаны в [contracts](contracts.md#f09-revision-aware-decision-contract).
Approval expiry также завершает human gate через durable resume; новая revision повторно
ставит resume, даже если job старой revision уже done. UI не отправляет execution grants.
