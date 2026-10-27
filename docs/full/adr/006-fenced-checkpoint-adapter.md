# ADR 006 — fence SDK persistence at its cursor transaction boundary

Status: accepted for F06, pinned dependency lock and migration 0007_execution_fences.

The installed AsyncPostgresSaver uses _cursor(pipeline=True) for aput and aput_writes, including blob
batches and the final checkpoint row. Its autocommit pipeline is not an ownership fence and is not
assumed atomic across those writes. A Python check before awaiting the SDK would allow a stopped
worker to resume after takeover and overwrite the new owner's checkpoint.

FencedPostgresSaver binds an immutable run/owner/epoch, replaces that cursor boundary with one
psycopg transaction and checks/locks workflow.run_execution_leases before yielding the cursor. The
same transaction performs every actual write. Database triggers recheck the fence on checkpoint,
blob and pending-write mutations, even if SQL bypasses the adapter. SQLAlchemy workflow projections
and MCP local reservations use the same helper/ownership row lock. Tenant and actor checkpoint RLS
remain additional constraints and cannot substitute for an epoch.

The lock order is ownership before action/command. Serialization holds only during bounded local
DB transactions, never around model/provider or HTTP calls. Heartbeat/reaper use the DB clock. A
transaction accepted before expiry holds the row until commit/rollback; takeover cannot interleave.

Alternatives rejected: API/worker singleton; a process mutex; heartbeat without write fencing; a
check before await; assuming the upstream SDK pipeline supplies transaction/epoch semantics.

The private SDK cursor extension is intentional and covered by actual SDK/graph compatibility,
rollback injection for blobs+checkpoint and pending-write batches, and late epoch rejection tests.
A dependency upgrade must pass these gates before rollout. Unsupported workflow/schema/checkpoint
state is needs_attention, without new operations. No promise of exactly-once external network effects
or F07 event delivery is added here. [Contract/runbook](../execution-fencing.md).
