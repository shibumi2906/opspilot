# F04 — API, execution and MCP authorization

Schema: 0005_authorization_context. Service context contract: version 1. OIDC remains the F03
BFF flow; internal service JWTs do not authenticate users and never forward IdP/browser tokens.

## Public surface

All /api routes require an unexpired server session and fresh memberships; mutations require exact
Origin and CSRF. Full V1 returns 410 after authentication. MVP V1 is unchanged in its original checkout.
Implemented V2: config/me/tenants, create/snapshot/decision, bounded history/counts, actions/evidence,
and membership administration. The run decision endpoint remains /runs/{id}/decision until F09's
revision approval contract; future clarification/cancel/SSE/connectors endpoints are not claimed here.

Operators create/read their own runs; approvers/auditors read tenant runs; only approvers decide;
admin has no implicit domain read/approval. Missing tenant/role is denied before object lookup.
Object UUIDs/evidence belong to the authorized run and tenant. History and total use the same tenant/
actor predicates. Opaque HMAC cursors bind tenant, user, filters and pagination position. Cross-user,
cross-tenant and tampered cursors are rejected. client_request_id replay also checks the persisted
actor before returning any existing run, and create responses link to the authenticated V2 snapshot.

Membership admin mutations use only the selected server tenant, validate target/roles, reject self
privilege escalation and record a security event. Headers/tool arguments never select tenant or role.
The admin role is rechecked under a DB membership lock in the mutation transaction.
Health/live/ready disclose only status, not DSNs, counts, users, checkpoints or provider responses.

## Execution context and checkpoints

The API still runs background tasks, with the existing single-process guard. Every execute/resume
loads actor and tenant from the persisted run and current memberships, not the approver's ambient
request. Local startup recovery scans the configured two-tenant demo catalog and opens a separate
owner-scoped saver per run. F05 will replace this with durable jobs/workers; no leases are claimed.

Every SQLAlchemy transaction resets tenant and actor context. Checkpoint connections set both on a
dedicated connection, validate actual Full database/schema and SDK migration level 9. Restrictive RLS
requires checkpoint thread → tenant/run → actor ownership, including the same tenant with a different
operator. Runtime checkpoint roles are not owners and cannot alter policies. F06 epoch fencing and
version-upgrade recovery remain separate work, not supplied by these actor predicates.

## Independent MCP boundary

MCP requires both its independent service bearer and an Ed25519 signed context. The context pins
issuer urn:opspilot:core:{local|test}, matching environment-specific MCP audience, version, actor,
tenant, optional run, iat/nbf/exp (60 seconds, two seconds verifier leeway), jti and scope. Only the
configured public key ring is read; unknown kid/algorithm/issuer/audience/lifetime is denied.
OIDC tokens, forged tenant headers and a bearer alone cannot create a valid context.

Read context has no action authority. The deterministic executor creates action scope only after
loading the immutable approved action, binding run/action/tool/exact argument hash. MCP independently
matches that binding and persisted approval, resolves current actor/approver memberships and self-
approval policy, then commits the local effect and receipt atomically. The actor remains the saved
operator, even when another user approved. No role claim from a model/browser is trusted.

Membership read/locks use identity.lock_role(uuid,uuid,text), a narrow SECURITY DEFINER helper with
fixed pg_catalog search_path and explicit current-tenant check. Runtime roles get EXECUTE/SELECT,
not UPDATE on memberships. Key-share locks serialize revocation against accepted local writes.
Role locks do not grant new memberships or bypass action policy. Readback/receipts still prevent
blind retries and duplicates. F09 revisions/grants/TTL and F12 full freshness/revocation scheduling
remain future stages; the internal 60-second context is not their complete approval protocol.

## Key lifecycle and minimum credentials

scripts/test-full-f04.ps1 builds the app and initializes an independent ignored key ring through
service-keys before starting services. For a fresh setup, generate Full .env, build, then run
`docker compose -p opspilot-full -f compose.full.yaml run --rm --no-deps service-keys`.
Linux setup makes only the output root writable to container UID 10001; private PEM files are 0600.

API/execution mounts .tools/service-keys/private read-only; MCP mounts only the public directory
read-only. MCP also does not receive the BFF session signing secret or identity gateway credentials.
Current/next keys overlap for rollout. To activate next, set SERVICE_ACTIVE_KID=next in Full .env and
recreate/drain API as appropriate. After old contexts drain, run the tools service with
`python -m opspilot.cli.service_keys /keys --retire current --active next` to remove its verification
key. Public JSON updates atomically through a directory mount and is reread for each request.
Never retire the active key. Tests rotate an isolated real MCP fixture; operational keys were not retired.
This two-slot local lifecycle is not a pilot secret-manager integration (F17/F23).

No tokens/keys/grants enter browser storage, graph state or public DTOs. Only bounded public
snapshots/evidence are returned; the checkpoint/role/credential stores have no public read route.
The deployment remains local/synthetic, with HTTP dev OIDC and local operator Jaeger. It is not
an externally exposed pilot, multiworker rollout, connector deployment or remote CI result.
