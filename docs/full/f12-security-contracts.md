# F12 freshness, expiry and bounded replan contracts

SEC-02/03/04 before implementation: authoritative PostgreSQL clock for approval/grant expiry;
same row locks serialize decisions, scheduler, revocation and dispatch. Current enabled actor and
approver roles are checked in Core and independently MCP, never taken from cache or old session.
Fresh MFA remains mandatory for hardened human decisions/revocation.

Each new revision binds an uncached bounded local configuration/monitoring precondition snapshot.
Core reads again before dispatch; MCP independently reads inside its local effect transaction with
configuration row share locks. Healthy means no longer required; unknown/error never satisfies a
precondition. Material drift supersedes the unexecuted revision, revokes its grants and creates one
new pending approval. At most one replan per run, including manual edits; no completed/unknown effect
can be replanned. Stable logical intents, completed sibling receipts and original DAG remain intact.
Legacy unexecuted revisions without snapshots require new consent, not silent baseline acceptance.

Monitoring is the existing local synthetic adapter, called directly each time; no cache and no vendor
writes. This stage does not establish a production monitoring connector. Verification has a separate
persisted bounded allowance, not research budget; uncertainty never retries a write. Key overlap uses
distinct version-bound current/next grant keys; removing a key invalidates it independently of JWT TTL.
Body-free audit/event/outbox projections and tenant RLS/fencing stay mandatory. Full ASVS L2 NOT_MET.


Numeric approval budget: a one-wave plan (or single intent) can use its second round for one
replacement decision. A DAG already reserving two dependency waves cannot allocate a third wave;
material drift stops the affected intent without dispatch/replan. This is enforced in Core and in the slot pointer
trigger; completed siblings remain recorded. Unavailable target/status may be previewed only as an
explicit unavailable marker, never as satisfied preconditions or a grant. MCP keeps its authorized
NOT_FOUND semantics for missing/foreign/disabled targets before consuming a grant; no domain insert
occurs until exact revision, roles, TTL, freshness, cancellation and signed persisted grant all pass.

Only configuration/project fingerprints and bounded status/IDs/role eligibility are exposed on approval cards;
raw customer metadata/project configuration is not copied into public snapshots. A current role
check, configuration share locks and fresh adapter reads are inside the effect transaction.
Legacy active approved runs in waiting_for_approval remain supported; terminal runs cannot issue
new effects. Legacy missing snapshots require new consent if round budget permits, otherwise stop.


Current monitoring checked_at must be within5 minutes of authoritative DB time, never future.
Direct local synthetic observation is requested at DB time, while returned source timestamps are
validated without rewriting them. Stale/future/naive/missing timestamps fail closed. This is not a
claim of a production upstream connector; its source-time contract remains mandatory for F18.
