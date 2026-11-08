# F21 local resilience evidence

2026-11-08, Ops checkout, branch `codex/opspilot-full`, base `152d59b`.
Authoritative outcome: [checks.json](checks.json). Overall F21 remains **blocked** on
unimplemented F20 Jira dispatch/one-attempt/reconciliation boundaries and the owner's
explicitly deferred real Jira acceptance. These local results do not close F20, Pilot
or whole ASVS L2. No Jira/vendor writes, paid model calls, remote CI or push.

## Accepted load

[load-soak.json](load-soak.json), isolated r4/subnet30/schema0021:

| Check | Measured result |
| --- | --- |
| Processes / tenants | 2 native API + 2 worker processes / 2 tenants |
| Concurrent replay burst | 100 creates for 20 identities, 100 decisions; 20 observed nonterminal runs |
| Distinct admission burst | 100 creates: 32 accepted, 68 bounded `429 RUN_ADMISSION_LIMIT`, zero 500 |
| Soak | 100 additional runs, 1800.009 actual seconds, 200 jobs independently counted |
| Tracked terminal work | 153 completed runs / 306 done jobs, including burst, quota and expiry probe |
| Local invariants | 0 duplicate, unauthorized, rejected-action writes, false verified successes or attention without reason |
| Create latency | p50 0.501 s / p95 3.177 s / max 3.225 s, 201 samples |
| Decision latency | p50 1.904 s / p95 3.876 s / max 4.144 s, 232 samples |
| Paced completion | p50 5.699 s / p95 8.625 s / max 16.836 s, 100 samples |

Active includes queue/human wait; this is not 20 executing workers. Replay samples
include bounded retries after injected failures. Distinct admission status counts have
their own denominator. The workload is paced at two runs per 36 seconds; this is not
a saturation throughput promise. Ten transport errors were recovered by idempotent
local command replay. Existing fixture sessions test BFF authorization, not IdP login load.

[Independent DB audit](independent-db-audit.json) ran before fault fixtures: the last
100 paced runs have exactly 200 jobs and zero active jobs. Global DB counts are 157
runs / 310 jobs because they include seed and two regression probes beyond the harness
tracked set. Registered external connectors: zero. Exact payload/approval ownership,
duplicate receipts, cross-tenant associations and unknown-job reasons were checked.

The approval observed through 1796.997 seconds had its normal 900-second TTL; it expired
during that interval. It was not pending for the whole half hour, and no consent was
inferred afterward. [Rolling probe](rolling-workflow.json) separately tests actual
legacy/new worker coexistence with pinned v1/v2 and naturally expired immutable revisions.

## Failures and recovery

| Durable boundary | Fresh evidence / scope |
| --- | --- |
| API commit before response loss | `test_api_commit_loss_offline_worker_and_singleton`; replay identity and singleton job |
| Worker pause/decision/write restart | `test_hard_process_recovery[pause/decision/write]` |
| Stale worker after kill/stop/DB-proxy partition | `test_two_workers_expiry_and_stale_boundaries[kill/stop/partition]`, fencing.xml |
| MCP/PG/Redis/collector outage | service-outages.json during actual soak; container stop-to-health |
| Synthetic provider timeout/unknown budget | governance tests; fake provider transport, no paid request |
| TTL, cancellation, opposite decisions and replay | freshness/action_grants/human_commands/new two-API races |
| Pinned versions / expired human wait | rolling-workflow.json plus half-hour observation in load-soak.json |
| Tenant/session/role/grant/SSRF/limits/telemetry | authorization/security_baseline/freshness/governance/SSE/observability + unit policy tests |
| Jira external write/one-attempt/lost-response reconciliation | NOT_MET: F20 implementation absent, real checks deferred |

The optional inherited Redis-outage test is skipped without its destructive fixture
flag. Actual Redis container outage is covered independently by the own-project soak
controller; the skip is retained and is not counted as a pass.

[Service outages](service-outages.json) stop each owned service for six seconds, then
measure stop-to-health: MCP 7.334 s, Redis 13.853 s, collector 15.807 s, PostgreSQL
10.440 s. Worker SIGKILL replacement 0.010 s measures spawn only; API replacement
9.743 s includes readiness. Durable recovery is evidenced by terminal work and separate
fencing probes, not by treating these two timings as equivalent.

[faults.xml](faults.xml), [fencing.xml](fencing.xml) and [units.xml](units.xml) contain
fresh execution outcomes. The final fault profile r6/subnet32 is separate from accepted
load. It uses inherited high fixture caps; load admission limits remain 32/40/64.
Final counts: 114 fault assertions passed / 1 skipped, 3 dedicated fencing cases passed,
278 unit tests passed. Functional local gates pass; security and overall F21 remain NOT_MET/blocked.
Negative stale-fence fixtures run in their own freshly prepared r7/subnet33 project.
The initial attempt on the mixed r6 fixture DB failed to obtain target claims within
20 seconds; all three failures remain in attempts/fencing-r1.xml. No timeout or claim
predicate was relaxed. The suite covers session/role/tenant denials,
opposite decisions and cancellation, grant/replay/TTL/freshness, API response loss,
worker stop/kill/DB-proxy partition, pinned workflow versions, SSRF policy and protected
telemetry. External Jira POST response loss/reconciliation is **not implemented/tested**.

Fault results use exact split collection coverage: the r6 run was manually interrupted
after 52 completed assertions when its slow output was misdiagnosed as a hang. Its raw
diagnostics are retained in attempts; unnamed interrupted cases are excluded from accepted
assertions. The resume helper checks all prior node IDs against the unchanged full
collection, runs only the remainder and merges only after exact unique coverage and a
successful exit. [faults-remainder.xml](faults-remainder.xml) remains independently visible.
Committed attempt XML removes only diagnostic trailing whitespace; byte-original copies
remain under ignored `.tools/f21-raw-attempts`. Test outcomes and traceback content are retained.

Two runtime defects were repaired: maintenance/admission lock inversion and per-request
enqueue pools. [Resource regressions](resource-regressions.xml) test both directly.
Migration0021 retains lifecycle shared locking and all worker admission predicates/ACL;
only the admission-exclusive key changes. No security timeout or immutable guard was loosened.

Failed candidates remain under [attempts](attempts): r1 checkpoint test setup, r2 lock
inversion, r3 pool exhaustion, and r5 immutable-expiry fixture rejection. They are not
accepted passes. The corrected expiry fixture configures TTL before revision creation.

## Machine, security and isolation

[Machine](machine.json): Docker Desktop Engine29.9.2, 12 visible CPUs, 8,144,474,112
VM bytes on the documented 16GiB host. [Resource sample](resource-samples.jsonl) near
minute19 recorded a cgroup kernel peak651,792,384 bytes, limit2,415,919,104 bytes,
zero OOM/failcnt, 42 PIDs. This is a sampled-container peak at that time, not a final
host-wide or end-of-run peak. No quorum, HA or promised SLO is claimed.

[Source provenance](source-provenance.json) records 152 actual imported application
source hashes; [image IDs](runtime-images.json) record existing pinned runtime images.
Tests use read-only current source/migration mounts; no new release image was built.
Main Full remains schema0019 and its deployment is unchanged.
[Harness provenance](harness-provenance.json) preserves the exact accepted load helper
as [load-r4.py](harness/load-r4.py). The final helper adds legacy-worker test options;
ordinary load defaults remain unchanged. Static results: [static-checks.json](static-checks.json).

[Security scans](security/checks.json) retain fresh raw vulnerability and Python audit
reports. [Secret scan](secret-scan.json) checks candidate artifacts and available labelled
F21 container logs against local exact secrets and JWT shapes, without exposing values.
Child API/worker stdio was discarded by the harness and cannot be retrospectively scanned;
protected telemetry tests and collector logs are separate evidence.

Security gate is **NOT_MET**: manager has one HIGH, `CVE-2026-78661`,
`golang.org/x/net v0.61.0`, fixed in0.62.0. No applicability exception is claimed.
App/PostgreSQL/Redis have zero HIGH/CRITICAL and Python audit reports no known
vulnerabilities. Rebuilding the large manager was deferred with less than3GB free;
preserved images/volumes were not pruned to make room. Future remediation needs a
separate manager image, fresh scan and manager/fault regression; existing measured
load used the recorded vulnerable image and must remain labelled accordingly.

[ASVS baseline](asvs-baseline.json): all253 inherited rows/fields/owners/N/A unchanged;
180 F21 scoped reviews do not close the whole requirements.
[MVP after](mvp-after.json) verifies184 source/env files, branch/HEAD, images, volume
metadata and read-only volume content against the preserved baseline.

Reproduce using [runner](../../../../scripts/test-full-f21.ps1) and
[contracts](../../f21-resilience-contracts.md). F21 managers have independent credentials
and volumes and attach only to their own lab network. Existing F17 manager connectivity
was not expanded. Preserve failed lab volumes/images; stop only owned F21 resources.
Final [cleanup](cleanup.json): zero running F21 containers; volumes, networks and images
preserved. Unrelated projects were not selected for cleanup.
