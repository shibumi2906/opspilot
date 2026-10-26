# Tenant foundation (F02)

The Full runtime database revision is `0003_tenant_rls`. This stage implements data isolation;
OIDC, server-session lifecycle and per-request signed MCP authority remain F03/F04/F09.
The deployment remains a localhost-only synthetic scaffold, not an authenticated public pilot.

## Identity and ownership

`identity.tenants`, `users` (unique issuer/subject), `tenant_memberships` (role allowlist), and
`sessions` form the identity schema. No login/session issuance is implemented here. Global users and
sessions have FORCE RLS with no runtime policies/grants; only the administrative migration role can
bootstrap them. Membership and tenant rows are tenant-owned and also use FORCE RLS.

Every existing domain table (including knowledge), workflow run/action/approval and SDK checkpoint
row has a non-null tenant key. Tenant/run carries actor_id and client_request_id is unique per tenant.
Composite foreign keys cover customer→integration/incident/ticket, run→action→approval/ticket, and
(tenant_id, thread_id) from all three checkpoint tables to the registered run. IDs remain opaque,
globally unique UUIDs; equal customer names are intentionally allowed in multiple tenants.

## Transaction and repository boundary

`tenant_scope(UUID)` is trusted in-process context, not a parser for browser/model input.
Every SQLAlchemy transaction calls parameterized `set_config('app.tenant_id', ..., true)`; no scope
sets an empty value. `identity.current_tenant()` returns NULL for absent/empty context and RLS denies
all tenant rows. USING and WITH CHECK protect reads, inserts and updates. Context is transaction-local
and assigned on every begin, including connections reused from the pool.

TenantSession adds SQLAlchemy loader criteria to ORM reads/updates, rejects another tenant's inserts,
and binds the session to one tenant. `get()` also checks the scope before consulting its identity map.
Raw retrieval SQL includes a tenant predicate. RLS remains the backstop for direct SQL.
Runtime workflow/domain/checkpoint roles are neither owners nor superusers/BYPASSRLS; only required
existing table/column privileges are retained. A stolen service/DB credential is not made safe by a
caller-set PostgreSQL GUC; verified authority/context is the separate F04 boundary.

## Local MCP scaffold

API and MCP each bind LOCAL_DEMO_TENANT from trusted server configuration (default synthetic A).
X-Tenant-ID, request text and tool arguments do not select tenant. The typed registry rejects extra
fields. The client refuses absent/mismatched trusted context before dispatch, so a run scoped to B
cannot accidentally collect evidence from an A-configured MCP instance. Tests start a separate B
MCP instance and use the real SDK/HTTP transport. This is not a multi-tenant service grant protocol.

The SDK uses one dedicated, non-pooled connection per checkpointer scope. It validates Full DSN,
actual current_database/current_schema, applies the trusted tenant setting, and closes the connection
on exit. RLS plus the composite thread FK prevents cross-tenant reads/writes. SDK DDL is frozen in
migration 0003 from locked checkpoint-postgres 3.2.0 (migration level 9). Runtime verifies this level;
it no longer calls saver.setup or owns tables/schema. SDK upgrades require an explicit administrative
migration. Lease/epoch fencing is still F06, not supplied by this tenant checkpointer scaffold.

## Synthetic fixtures and upgrade

Tenant A: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa; B: bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.
Both have GreenShop, BlueMarket, GreenShop EU, 10 incidents, 5 knowledge articles, and a known fixture
ticket. A retains original customer/integration IDs; B uses uuid5(B, original_id). Both have disjoint
uuid5(tenant, seed-run/seed-action/seed-ticket) rows. Seeds are administrative, explicitly synthetic,
idempotent, and do not replace unrelated operator data or copy MVP runtime data/credentials.

Migration 0003 maps only the frozen known fixture customer/integration/incident/article IDs and known
synthetic scenario runs to tenant A. Unknown ownership aborts and transactionally rolls back. Legacy
checkpoint threads must reference a mapped run. In opspilot_full_test only, historical F01
compatibility-UUID SDK probes receive explicit synthetic run registrations; arbitrary orphan threads
still block migration. No existing MVP database is read to construct upgrade fixtures.

`tests/full_migrations` starts at frozen revisions 0001/0002, inserts reproducible legacy data including
a pending workflow snapshot/checkpoint and ticket, and compares every original field after upgrade.
The separate fresh-schema case also checks checkpoint-role access after ownership transfer.
Destructive fixture resets require APP_ENV=test, exact DSN and actual opspilot_full_test identity,
and an explicit migration-project flag. They run in opspilot-full-f02-migrations, not in the live Full
or MVP database. Downgrade is deliberately refused; recovery uses an isolated restore and reconciliation.

## Commands

From the existing Full worktree:

- `powershell -NoProfile -File scripts/test-full-f02.ps1`: build, migration gates, lint/types,
  backend, browser, process-recovery and 12 scripted regression evals.
- Stop Full API/MCP/web before migration: `docker compose -p opspilot-full -f compose.full.yaml stop api mcp web`.
- `docker compose -p opspilot-full -f compose.full.yaml run --rm admin`.
- `docker compose -p opspilot-full -f compose.full.yaml run --rm admin python -m opspilot.cli.seed`.
- `docker compose -p opspilot-full -f compose.full.yaml up -d --wait postgres collector jaeger mcp api web`.

Migrations and schema management belong to the administrative image/role; do not auto-generate drops
for the SDK-owned-by-migration checkpoint schema from application ORM metadata.
F02 evidence belongs under evidence/f02; F01 reports and all MVP artifacts remain separate.

## F04 current boundary

F04 supersedes the fixed local MCP scope/V1 baseline described above. Authenticated V2 and signed
per-actor/tenant/run MCP context are implemented; see [authorization.md](authorization.md).
API background execution is still not F05 durable workers; F06 fencing remains future work.
