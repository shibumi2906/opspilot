# F16 local observability runbook

Start in Ops, read the canonical tracker and run the MVP isolation gate with explicit mvp_path.
Preserve .env and existing private keys. Prepare missing telemetry identities once:
python scripts/setup-full-f16-observability.py (add --test for acceptance).
Existing/partial credentials are never rotated implicitly. CA private key stays ignored on host.
Leaf certificates last60days, local CA90days; planned controlled rotation is required before expiry.

Default dev project is opspilot-full; acceptance project must be opspilot-full-test-*.
The receiver has no public port. Open the authenticated Diagnostics view from a run's trace link
or navigation. Tenant overview follows current role; operator is actor-scoped. Graph/command
rows expose IDs/epoch/link, never raw prompt or request. Legacy commands may lack trace context.
A missing trace can mean bounded retention, dropped export or legacy work; inspect durable state.

| Condition | Inspect and respond |
| --- | --- |
| QUEUE_AGE >=60s / DEAD_COMMAND | Check running worker and DB readiness, command attempts/reason, pending time and eligible tenant. Restore worker; do not duplicate a write manually. |
| LEASE_EXPIRED / lease churn | Compare DB lease expiry/epoch and worker status. Existing reaper/fence recovers ownership; never clear lease/epoch or replay a dispatched write by hand. |
| UNKNOWN_OPERATION | Use existing reconciliation/status/receipt workflow. Never treat telemetry absence as proof a write did not occur. |
| AUTH_DENIAL_BURST >=5/min | Review scoped security audit reason/request IDs and live membership/IdP state. Do not relax CSRF/session/service grants to clear an alert. |
| BUDGET_DENIAL | Inspect durable usage/attempt state, configured limits and known/unknown usage. Collector/Redis restart cannot refund the ledger. |
| COLLECTOR_UNAVAILABLE / COLLECTOR_BUSY / EXPORT_FAILED | Check collector container, native TLS expiry/trust/hostname and role token file mounts without printing values. Core DB admission stays active. Redacted Docker diagnostics and PG audit remain available; bounded queues may drop telemetry. |
| METRICS_STALE >10s | Check service heartbeat/exporter status. Traces succeeding does not prove metrics health. Restore source export; no fabricated zero values. |
| SOURCE_CLOCK_SKEW >30s | Compare source/receiver UTC and host/VM NTP. Regression>5s quarantines receiver writes; investigate clock before restarting. |
| COLLECTOR_INTEGRITY_FAILED | Restrict access, stop receiver, preserve data+seal+logs and record hashes in protected storage. Investigate tamper/storage/clock before restoration. Restore only an independently verified paired database/seal backup under the original key, then verify. Never delete/reset journal to obtain green. |
| TELEMETRY_RATE_LIMIT | Identify misbehaving role/process and bounded exporter counters; investigate volume without logging payloads or disabling protection. |
| Proxy errors | Inspect safe error category, request ID/status/time and API readiness. Error logging stays enabled; raw header/URI disclosure is not needed for triage. |

Reproduction: scripts/test-full-f16.ps1 (regression), scripts/test-full-f16-tls.ps1 (native TLS/MFA),
scripts/test-full-f16-observability.ps1 (collector native authentication, sentinel, outage and
isolated-volume tamper/recovery drills). Fault runner accepts only a named Full test project
and preserves paired original/corrupt copies under ignored .tools. Do not run it against dev.

These thresholds are checked locally against actual queues and injected failures. A visible
dashboard condition is not delivery to an on-call service. Production paging, archival/legal
retention, independent backups, host access review, immutable remote anchors, clock monitoring,
capacity/soak and disaster recovery remain deployment-stage evidence. Full ASVS L2 NOT_MET.
