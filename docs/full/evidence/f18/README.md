# F18 — accepted adapter platform and signed ingress

Base `017b68bb34e85e95013076d570bd14b5519f842b`; independent Full checkout/branch.
Schema0019; canonical MCP13 tools, graphs v1/v2, DTO/state1 and checkpoint SDK9 retained.
Commit subject: `feat(full): complete F18 adapter platform and signed ingress`.
Only F18 is closed. F19–F24 not started; Full Pilot and whole ASVS L2 **NOT_MET**.

[Measured checks](checks.json), [contracts](../../f18-security-contracts.md),
[operations](../../f18-operations.md), [crypto inventory](../../f18-crypto-inventory.json).

## Implemented

Tenant-admin CAS config and immutable deterministic mapping1, computed secret refs, real manager
credential/webhook ACL separation, exact registered paths, bounded HTTPS adapter and persisted
circuit breaker. Simulator remains explicitly synthetic; external write/native idempotency false,
credential expiration unknown. Model/callback cannot supply a URL, secret ref, approval or business write.

Raw-body tenant/connector/timestamp-domain-separated HMAC256, key overlap/retirement, constant-time
check, DB-clock window, immutable event/body identity. Receipt+job commit before2xx; duplicate200,
altered body409, monotonic processing ignores older observations. Separate no-business-privilege
worker and eight FORCE-RLS tables. Public edge preserves signed bytes and bounds method/body/time.

## Acceptance

- Real transport33/33: actual HTTPS API/simulator, manager and PostgreSQL; invalid signature/time/
  scope/approval payload, replay/conflict/out-of-order, kill before commit/after commit before ack,
  processor kill and two-worker claim, DNS pin/rebinding/private addresses/redirect/TLS/body limits,
  persisted breaker, tenant/global quota and public proxy.
- Full backend486/44 dedicated skips; unit200 included in backend and independently passed.
  The33 F18 cases run separately;11 inherited specialized skips retain their dedicated gates.
  Ruff/format223/mypy146; [installed-source/proxy match](source-image-match.json).
- Browser24; queue5; fencing3; provider crash1; Redis stop/recreate1; scripted eval12/12,
  zero unauthorized writes/duplicates/forbidden calls/false verified success.
- [Real manager](manager/checks.json):9 exact-path service/tenant ACL assertions, HMAC overlap,
  h1 retirement/h2 continuity, accepted h1 jobs processed after retirement, original ring CAS
  restoration and revoked-token fail-closed. Operator root/unseal material never enters app mounts.
- Native TLS8, collector12, Redis6, MFA14 and separate IdP policy4. New
  [TLS edge](tls/f18-ingress-edge.json) and [positive ingress](tls/f18-positive-ingress.json)
  prove actual HTTPS edge/API/manager, verify-full Postgres role and minimal-environment CLI processing.
- App/web/Redis/IdP/Postgres/manager raw HIGH/CRITICAL0; Python/npm audits pass. Fresh raw scans under
  regression/security and security; [inventory](inventory.json) verifies unchanged F17 runtime IDs
  for Redis/IdP/Postgres/manager. No ignore or applicability exception used for these results.
- [Database invariants](ingress-db-state.json):8 FORCE-RLS tables, no domain/workflow privileges,
  no config mutation by readers, no PUBLIC execute on privileged functions, consistent receipt/job/cursor.
- [ASVS preservation](asvs-baseline-check.json):253 inherited rows/fields/owners/baselines/N/A intact;
 102 scoped reviews and5 primary local contributions; whole norms remain open.
- [Artifact](artifact-secret-check.json) and [21-container runtime](runtime-secret-check.json) checks:
  zero actual credential/private-key/sentinel matches; no secret values exported.

## Existing Full and MVP

[Encrypted backup + fresh offline restore](backup-restore.json), then
[count/SHA256 comparison of all48 legacy tables and columns](rollout-preservation.json) before
workers/smoke. No seed or implicit customer adapter registration. Existing verified F17 logical PG
volume used; original Full volume retained. Full schema0019, empty default adapter registry,
[isolated observation worker](worker-isolation.json), real OIDC/scripted/refresh/diagnostics smoke and
[UI/API200](restored-full.json). [MVP final isolation](mvp-isolation.json) matches tracked files/env/
branch/HEAD/images/volume metadata and read-only volume content. Test profiles stopped; data preserved.

## Verification history and limits

Early positive transport failures exposed FOR SHARE privilege requirements: replaced with a narrow
trusted-tenant lock function rather than granting readers config mutation. Tampering fixtures still
read obsolete file grant keys; corrected to sign altered claims with the actual configured manager
key. Final full backend passes. Canonical no-store proxy response fixed and signed edge test passes.

The backend negative-fencing fixture retained a superseded claim. It was preserved, not repaired/
deleted for a green browser result: [metadata and fresh-database separation](fixture-queue-separation.json).
Final browser/process acceptance passed on its own seeded database. Interrupted/failed attempts
remain in ignored local logs; accepted measurements above come from final passing executions.

Concurrent labs exhausted host memory and stalled Engine; the already-authorized restart preserved
all data and restored services. Checks resumed serially. Native automatic network pools were exhausted;
an explicitly checked subnet was allocated without deleting preserved networks.

No paid model calls, vendor writes, remote CI, push or production deployment. Simulator real HTTP/TLS
boundaries do not constitute a vendor/staging/live gate. Manager tokens last1h and need explicit
operator refresh; enrolled worker tenants require trusted configuration. Retained receipt caps fail
closed without deleting replay identities. Load/soak, real/holdout eval, production firewall/recovery,
independent release/N/A reviews and full ASVS L2 remain future gates.
