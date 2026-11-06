# Local Full Core lifecycle and recovery

Use `compose.full.yaml` plus `compose.full.f17-local.yaml`, project `opspilot-full`.
The local override selects the logically restored PostgreSQL volume through ignored
`FULL_F17_PG_VOLUME` and mounts only service-context keys plus narrow manager credentials
into workers. Do not start the old physical volume with the new Alpine runtime.
The preserved `opspilot-full_pgdata` and `postgres:f16-before-f17` belong together.

Normal restart, without seed or migrations:

```powershell
.venv/Scripts/python.exe scripts/setup-full-f17-manager.py --local
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml up -d --wait postgres redis oidc collector mcp api worker worker2 web
```

Manager setup preserves signing identities and replaces one-hour nonrenewable service
tokens. Refresh before expiry; expired, revoked or unavailable manager access denies new
grant issuance. Root token, unseal shares, CA/server private keys and backup keys stay in
ignored operator recovery files. Never mount that directory into API, workers or MCP.
The test manager uses independent state and loopback port18200; development uses18202.

## Retention and export

No automatic retention runs on the existing Full data. An operator with the dedicated
migration connection must identify an active administrator of the selected tenant.
Project defaults are evidence30/history90/audit365 days, batch20 (maximum100).
Periods must be ordered. These are configurable project choices, not legal requirements.

```powershell
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml run --rm --no-deps admin python -m opspilot.cli.lifecycle preview --tenant TENANT_UUID --actor ADMIN_UUID
```

Review the candidate IDs, levels, policy and `preview_hash`. Apply requires the same
tenant, actor, periods and batch size plus `compact --preview-hash HASH`. Any changed
candidate set rejects the apply. `export` returns at most100 allowlisted metadata rows
for that tenant; no request bodies, action payloads, checkpoints, tokens or secret values.
The existing authenticated audit export remains scoped by F14 roles and positive schema.
Preview, compact and export append body-free administrative security events.

Pending approvals/jobs, unknown operations and live leases prevent compaction. Runtime
transactions drain under a bounded maintenance lock before eligibility is evaluated.
History erasure is irreversible. Keep identity hashes, original command identities,
operation result references and deletion tombstones indefinitely to deny resurrection
and duplicate writes. Domain tickets/comments/notifications remain business records;
their deletion and user/tenant removal require a separate reviewed workflow.

## Rotation and recovery

Grant rotation order: create immutable private version, publish public verification
overlap, switch active reference, let existing grants finish within their60-second TTL,
then remove the old public entry. Emergency revocation removes the public entry and
revokes affected service access immediately. Reconcile unknown operations by their
persisted receipt before retrying. Active-reference rollback is explicit; never restore
a compromised key automatically. `test-full-f17-manager.py` checks rotation/revocation,
ACLs, sealing, restart and fresh-instance encrypted snapshot recovery. The separate
in-flight coordinator pauses two real claimed jobs after grant issuance, rotates the
manager key, then verifies each actual MCP write exactly once.

The local PostgreSQL transition uses an offline encrypted physical backup restored
with the original image, then encrypted logical dumps restored into a fresh no-network
PostgreSQL16 volume with `C.UTF-8` collation and rebuilt indexes. Every column of the15
legacy tables is fingerprinted before/after. Source volume and encrypted recovery
artifacts are retained. No retention was applied to the existing Full database.

For rollback, quiesce API/MCP/workers first. The old physical volume is a historical
snapshot: it cannot replace a newer writable database without reconciling subsequent
business effects, command identities and deletion tombstones. Restore newer tombstones
and erasures before enabling writes; never replay erased commands from an older backup.
F23 retains the production/off-host recovery and deployment acceptance scope.

Full Pilot F18–F24 and complete ASVS L2 acceptance remain NOT_MET. All local application
checks use scripted models and synthetic data; no paid model or vendor writes are enabled.
