# F11 mixed plans security contracts

Before schema/runtime: only local tools; max3 actions, max2 approval waves, immutable tenant/run
plan, stable per-run business-intent keys, no duplicate intents, unknown dependencies or cycles.
A deferred comment is not an executable approval: Core must bind a verified created ticket ID,
create a distinct immutable revision, then wait for a separate persisted human decision.
No proposal/rejection/approval for one slot grants authority to another. Each MCP effect checks
current plan membership, complete decisions for its wave, verified dependency receipts and exact
revision binding in its transaction. Core checks the same before issuing its separate signed grant.

SEC-03: every slot retains F09/F10 actor/role/tenant/TTL/fence/recipient/target checks. Plan metadata
is included in immutable revision digest. Completed effects are never replanned or dispatched again;
identical plan preparation reuses slots, a changed plan conflicts. Unknown/mismatched effects block
dependents. Partial decisions persist without dispatch until the wave is fully decided.

SEC-07: bounded typed JSON (3 nodes,2 dependencies/node,2 waves,3 verification reads/slot), bounded
sequential graph, DB persisted verification reservations survive restart. Durable resume successor
prevents a second-wave decision racing a running job acknowledgment from being lost. No additional
unbounded queue, Redis, connector or research work. Existing research/time/token limits are retained.

Compatibility: existing v1 workflows/checkpoints keep v1 graph. Explicit mixed requests use pinned
full-graph-v2; no silent checkpoint reinterpretation. F12 replanning/freshness and F14 full inbox UI
are not implemented. F11 public projection exposes per-slot decision/effect/verification; global
verified success is possible only when every requested slot is independently verified.
Bodies remain tenant confidential and React text; events/audit carry only identifiers/status/wave,
not plan bodies or credentials. Full ASVS L2 remains NOT_MET; accountable future owners unchanged.


Local planner routing: explicit notify/inbox/comment requests receive v2; other/previous workflows
stay v1. Core picks a bounded enabled tenant-approver recipient, never an arbitrary model recipient.
The immutable F11 plan cannot be edited through the legacy revision endpoint; F12 replan is future.
Verification reservations are separate from research allowance and aggregate into snapshot usage.
