# F16 — observability and operator diagnostics security contracts

Scope: Full checkout Ops, base a06d1a7 (accepted F15 4733998), schema0017_observability.
F16 changes telemetry and operator projections; business authorization, grants, consent,
verification, pricing and durable resource ledgers remain authoritative in PostgreSQL.
No F17 work, paid provider call, production deployment or push is authorized by this stage.

## Trace lifecycle and privacy

API starts a new trusted trace; external traceparent cannot select another user's trace.
Enqueue persists only W3C traceparent in the command transaction. Each claimed command starts
a new root linked to that context, with database run/job/actor/tenant/epoch identities.
Persisted actor resolution and existing execution fencing govern graph/LLM/MCP execution.
Worker completion, failure or human interruption ends that span and releases ownership.
SQL spans require a live recorded parent: idle worker/SSE polls do not create standalone traces.
Active API/job/MCP SQL remains traced, including error status without SQL text. Idle database
failures retain worker error diagnostics and upstream-error metrics.
Continuation in another process receives a new trace and a durable link; a human wait does
not retain a process or span. SSE request tracing ends at response headers, not at human reply.
Graph, provider, signed MCP, adapters, verification and reconciliation emit correlated spans.

Source exporters AND authenticated ingress apply the same positive schema. Only fixed span
names/events/tool/reason/phase enums, valid UUIDs, nonnegative bounded numbers, trace IDs and
up to8 links survive. Arbitrary messages, SQL, prompts, outputs, documents, URLs/query strings,
exception text/stack, tokens, cookies, authorization and service settings are discarded.
Resource service name comes from receiver credentials, not the supplied payload.
Metrics have fixed names and bounded enum labels; no actor/tenant/run labels. Service receipt
state is the latest service-level heartbeat, not per-instance health; use durable DB lease/epoch
diagnostics for worker ownership. Upstream/error
counts shown to operators come only from their bounded100 authorized retained records (workflow/security first, DB/HTTP fills remaining slots) and are
explicitly partial; scoped authoritative queue/usage values come from PostgreSQL.

## Protected local transport and storage

The F16 receiver implements the explicit OTLP/protobuf subset used by OpsPilot, not the full
OpenTelemetry Collector distribution. Traces/logs/metrics use native TLS, trusted independent
CA, hostname verification, required client certificate and a separate64hex bearer per role.
No public listener/port or default Jaeger UI is published. API/probe may read; worker/MCP export
identities cannot read. Only API brokers user reads after live SQL authorization. Probe identity
is mounted only in tools/tests. Each runtime gets its own client material, never the CA key,
server private key, receiver hashes or integrity key.

Collector is nonroot10001, read-only filesystem, no capabilities/new privileges,192MiB,
16 HTTP concurrent slots,4 bounded journal tasks on one fair serial executor,262144byte bodies,2s input deadline,
1000requests/identity/minute,128records/request. Client queues256spans/256logs, batches32,
HTTP export deadline300ms and no transport retry. Authorized diagnostics query has a2s deadline. Export failure cannot block approval or change a
fence; drops/failures are counted. Redacted rotated Docker logs and PG audit remain independent.

Metadata journal: separate dedicated Docker data and seal volumes,600files/700directories,
SQLite synchronous FULL,32MiB logical database ceiling,10000records and24hour maximum age on
append. Per-record HMAC chain and separately sealed head detect modification, deletion,
truncation, database rollback and invalid seal; two-phase seal detects an incomplete transition.
Reads use a single SQLite snapshot and append acquires BEGIN IMMEDIATE before verification;
external writers cannot cross the verified boundary. Reads/writes verify and quarantine failures. A2s monitor removes readiness after integrity
failure. New writes never silently reset a corrupt journal. HMAC protects against data-only
tampering; a host administrator controlling BOTH volumes AND integrity key can replace them.
External immutable anchoring/managed secrets/backups are deployment obligations, not claimed here.

Source timestamps and receiver UTC are stored separately. Database metrics use database time.
Source trace skew>30s is flagged; receiver clock regression>5s quarantines new writes.
Host NTP/VM drift monitoring remains operator responsibility; local tests do not prove production
clock synchronization. Retention pruning preserves a signed prefix boundary. Local Docker
logs use local driver5MiB x3 for app/web; they are a bounded fallback, not a permanent audit archive.

## Log inventory and ownership

| Layer | Data and purpose | Access/storage/retention | Accountable owner |
| --- | --- | --- | --- |
| API/worker/MCP | Safe severity/event/code/UUID/trace diagnostics and allowlisted exception class | Redacted stderr + protected collector; bounded Docker rotation /24h10000metadata rows | Application operator |
| Nginx | Generated request ID, method, status, duration; safe error category | FIFO sanitizer before Docker driver, same bounded rotation; no raw path/header/body | Platform operator |
| Security/identity | Existing login/session/tenant/authorization/security reason records | Role-restricted PostgreSQL audit; existing immutable application audit and RLS; durable DB retention requires approved archival | Security operator |
| Run/action/command | Durable decisions, fencing epochs, verification/reconciliation status | Tenant/actor DB authorization, existing append-only audit/events; no F16 deletion | Application operator |
| Collector | Authentication/parse/rate/integrity counters, source/receipt times | Private receiver, HMAC journal and separate seal; API/probe read only | Security operator |
| PostgreSQL/Redis/IdP | Existing engine/security diagnostics; database and identity authority | Existing private/native TLS lab controls; host Docker access is privileged; deployment retention/export remains separately reviewed | Database/identity/platform owners |
| Browser/operator export | Only live authorized metadata, safe status codes | No-store, existing session/tenant revocation, React text escaping; user-managed downloaded metadata | Tenant operator |

Nginx errors remain enabled. The wrapper retains UPSTREAM_UNAVAILABLE, UPSTREAM_TIMEOUT,
TLS_HANDSHAKE, REQUEST_REJECTED, FILE_ACCESS and PROXY_ERROR categories plus control notices;
access records retain status/duration/request ID. It deliberately omits arbitrary raw error
strings. Known Python exception classes and security event/reason enums retain useful failure
diagnostics. Unknown class/text does not become a log injection channel.

## Access, alerts and failure behavior

Only operator/admin/auditor can open diagnostics. SECURITY DEFINER projection has fixed
pg_catalog search_path, PUBLIC revoke and narrow ops_workflow execute. It checks live
membership under database locks; operator sees own runs, admin/auditor tenant scope.
Missing/foreign run is404; approver403; unauthenticated401. Collector queries inherit the
database's actor scope, never a browser-supplied tenant or role. Process-wide business metric
values are removed from browser responses. Telemetry is not business authority.

Dashboard conditions are project thresholds, not measured SLOs: queue age60s, expired lease1,
dead job1, unknown operation1, denial burst5/minute, exhausted active budget1; exporter failure,
collector outage/integrity failure, metric heartbeat older10s, source clock skew30s and rate
limit are visible. Dashboard polling is an operator aid, not a production paging service.
See [runbook](f16-observability-runbook.md) for triage and verified drills.

## SEC-01/10 and ASVS claim boundary

No whole-requirement closure is claimed. All253 protected IDs/levels/baseline assessments,
accountable stages, N/A rationale and owner review fields must match base. SEC-05 primary
reviews record scope and residuals for16 requirements; common controls are rechecked for
changed surfaces. The full L2 result remains NOT_MET. F17/F23/F24 still own deployed PKI/
secret manager, external anchoring/retention/clock/paging/load evidence and whole-system review.
Fresh image/package audits retain raw findings and exact-image IdP applicability, no scanner
ignore, metadata removal or risk acceptance. Public evidence must contain no credentials or
raw customer/request payloads.

Technical references: [OTLP exporter protocol](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/protocol/exporter.md),
[Python OTLP SDK](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html),
[SQLite transactions](https://docs.python.org/3/library/sqlite3.html).
