# F17 — accepted local Full Core

Base `6330f32`; `C:/Users/user/Desktop/code/Ops`; branch `codex/opspilot-full`.
Schema `0018_lifecycle`; graphs v1/v2, DTO/state1 and checkpoint SDK9 remain pinned.
Only F17 is closed. Full Pilot/F18–F24 and whole ASVS L2 remain **NOT_MET**.
Commit subject: `feat(full): complete F17 lifecycle and Core security acceptance`.

[Measured acceptance](checks.json), [security contracts](../../f17-security-contracts.md),
[operations/recovery](../../f17-operations.md), [crypto inventory](../../f17-crypto-inventory.json).

## Implemented and verified

- Operator-only tenant-admin retention preview/apply, exact policy/candidate digest,
  bounded30/90/365-day project periods and20/100 batch bounds. Pending/unknown/jobs/leases
  survive. Shared runtime/exclusive maintenance locks serialize eligibility and erasure.
- Evidence/checkpoints, history/action/human-command payload erasure, metadata export and
  body-free administrative audit. Reserved run/command/operation identities, hashes and
  result references/tombstones deny resurrection and duplicate local business writes.
  Domain tickets/comments/notifications remain independent business records.
- Real non-dev TLS OpenBao with encrypted Raft, narrow worker/MCP/tenant ACLs, nonrenewable
  one-hour service tokens, signing overlap, revocation, seal/restart and fresh encrypted
  snapshot recovery. [15 real checks](manager.json), [two claimed jobs across rotation](inflight-jobs.json).
- Scoped ASVS contributions:102 reviews/24 primary contributions, all253 protected inherited
  fields/owners/N/A unchanged. [Baseline proof](asvs-baseline-check.json).

## Acceptance results

The initial full backend run had451 passes,1 observability admission failure and11
special process skips. This is recorded, not presented as an entirely green first run.
The final affected regression passed16/16, all172 unit tests passed, and Ruff/format/mypy134
passed. New tests prove bounded trace retry only for explicit pre-admission rejection and
no retry for unknown outcomes. A real saturated journal executor proves rejected work was
not submitted. [Pressure investigation/resolution](trace-pressure.json).

Browser24; queue5; fencing3; provider crash1; [Redis stop/recreate1](redis-restart.json).
Final native [TLS8](tls/tls-probes.json), [collector12](tls/collector-native.json),
[Redis6](tls/redis-tls.json), [MFA/browser14](tls/browser.json), [IdP policy](tls/idp-policy.json).
[Scripted eval12/12](evals/scripted.json), with zero paid calls, unauthorized writes,
duplicates, forbidden calls or false verified success. These are local scripted results;
no real-model quality or F21 load/soak claim is made.

Final source logs remain ignored under `.tools`: `f17-core-r8.log`,
`f17-admission-targeted.log`, `f17-admission-unit.log`, `f17-after-backend-r8.log`,
`f17-admission-tls.log`, `f17-admission-security.log`, `f17-release-smoke.log`.
Structured public results and exact runtime IDs are committed here.

## Supply chain

[Six exact runtime scans and package audits](security/summary.json): raw HIGH/CRITICAL0
for app/web/Redis/IdP/PostgreSQL/manager; Python/npm vulnerabilities0, CVE exceptions0.
[Package/source/image inventory](inventory.json), [local runtime IDs](local-runtime-images.json),
[native runtime IDs](tls/runtime-images.json), [manager patch proof](security/manager-patch-proof.json).

Rejected official manager and inherited PostgreSQL/web/IdP candidates remain under
`security/candidate-*`; they are not accepted runtime results. The manager preserves
Go module metadata and carries a tested bounded-RSA backport plus updated go-jose/v4.
PostgreSQL remains major16 with a rebuilt gosu/Go runtime; web uses fixed expat; IdP keeps
Keycloak26.8.1 on security-fixed Java21 Alpine. All482 Keycloak JARs are byte-identical
across the runtime change ([proof](security/idp-jar-continuity.json)). The949MiB fresh Java
artifact-index download exceeded the first scanner deadline; the fresh retry and final
combined scan passed. Both scanner database timestamps are recorded; no CVE feed was skipped.

## Existing Full and MVP preservation

[Encrypted physical backup/fresh offline restore](backup-restore.json) uses the original
PostgreSQL image. [Logical libc transition](logical-postgres-restore.json) restores into a
fresh no-network volume. All15 legacy table counts/hashes match before and after the
schema migration, measured before workers/smoke ([proof](rollout-preservation.json)).
The original Full physical volume and encrypted recovery material remain preserved.
No retention was applied to existing Full. Keys and credentials remain ignored locally.

The final [real OIDC/scripted smoke](live-diagnostics.json) passes usage/refresh/history
and a durable command trace with verified collector integrity. Two workers and local
API/UI are healthy. [MVP gate](mvp-isolation.json) proves184 files/env, main/HEAD f9f8d79,
image tags and volume metadata/content unchanged. Test profiles are stopped; local Full
remains available. Docker restart earlier in the task was explicitly authorized.

Only public software/advisory downloads and synthetic local application traffic occurred.
No paid LLM calls, vendor writes, remote CI, production deployment or push.
Production custody/off-host recovery, operational load/soak and whole ASVS L2 remain open.
Manager service tokens require explicit operator refresh after one hour; bounded telemetry
is operational evidence and cannot replace durable job/audit/receipt authority.
