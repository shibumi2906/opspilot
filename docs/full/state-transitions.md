# State transitions (Full v1 draft)

Machine-readable normative table: [state-transitions.json](state-transitions.json).
Contract tests validate closure, terminal non-revival and allowed action combinations.
This is a design contract for later stages, not a replacement of the F01 inherited runtime.
An absent edge/combination is forbidden. Idempotent replay returns the persisted response without a transition.

Run status describes scheduling, outcome describes business result (§7). completed/cancelled/failed never
return to running; GET/reconnect never transitions any state. needs_attention permits only explicit
operator reconciliation, which cannot re-dispatch an unknown write. Queued resume requires a durable command.
waiting states persist before releasing ownership. Cancelling waits for already accepted effects and reconciliation.
completed outcomes: diagnosis_only, actions_verified, actions_partially_verified, rejected, expired,
blocked, insufficient_context, budget_exhausted, partial. Cancelled has no business success claim;
unknown_outcome requires reconciling/needs_attention, not a verified completion.

Every edge additionally requires tenant authorization, expected version, allowed command and ownership.
Approval pending → approved/rejected requires current membership and DB-time TTL; expiry/revision/cancel
serializes on the same row. approved → expired/superseded/cancelled only affects undispatched work.
After dispatch, expiry/cancel can coexist with a completed effect; they do not revoke historical authority.
Rejected/expired/superseded/cancelled approvals never become approved again; create a new revision.

reserved requires an approved exact revision and a live fenced lease. dispatch_started records the boundary
before calling transport. A definitive failure becomes failed; transport ambiguity becomes unknown.
unknown → succeeded/failed is reconciliation evidence only, never another dispatch.
succeeded records a receipt, not verified business success. Verification can resolve unknown/unavailable
with bounded reads; verified and mismatch are final for the revision. mismatch does not authorize retry.
Dependencies rejected/expired/cancelled cause skipped_dependency; no effect is sent.
