# F19 local Prometheus read connector

Only the local part is authorized. Staging/live acceptance is blocked: the user explicitly
deferred the separate staging target and credentials. Full Pilot and whole ASVS L2 remain NOT_MET.

## Scope and data semantics

The operator registers an exact tenant/connector/customer/integration tuple, canonical HTTPS
origin (443/8443), all permitted numeric addresses, explicit CA, expected targets (1–8), auth
scheme and deployment/dataset labels in an absolute JSON file (`PROMETHEUS_REGISTRY_FILE`).
Duplicate registrations/JSON keys, extra fields, unsafe addresses and fixture production use
fail closed. Private addresses require explicit operator permission; loopback, link-local,
metadata, unspecified, multicast and IPv4-mapped addresses remain forbidden. Registration is
empty by default. Admin may toggle registered reads with CAS/recent-MFA controls; admin/model
cannot select arbitrary PromQL, URLs, headers, secret refs or a different mapping.

The only metric is `opspilot_integration_health` scoped by exact UUID labels, job `opspilot`
and a bounded expected-target allowlist (literal safe names in a fully anchored label matcher).
Operators must supply its semantic contract: 1 healthy, 0.5 degraded, 0 unavailable, with
`opspilot_target` identifying every expected target. This is a business integration health
gauge, not the exporter scrape `up` metric. A fixed composite expression returns both health
and `timestamp(metric)` in one evaluation. Evaluation time never substitutes for sample age.
All expected targets and timestamp/value pairs must be present and no older than120s (5s
future clock tolerance); otherwise current health is unknown. Credential expiry is always
unknown. Transport errors/warnings/infos fail as dependency unavailable; they do not prove an outage.

Events are explicitly observed/synthetic metric samples, not historical business events.
Repeated samples have deterministic identities. Missing/partial/stale ranges produce diagnostic
unknown evidence, never fabricated HTTP errors. Provenance is
`prometheus-mapping1:{synthetic|observed}:{fixture|staging|live}`, persisted and displayed through
the existing MCP13/DTO1/graph contracts. A real engine reading generated series stays synthetic.

## SEC-04/09 and common SEC-01/10

- Credentials come only from exact manager `connectors/{tenant}/{connector}/credential`, with
  matching record metadata; scoped service ACL denies webhook, foreign tenant and unknown connector.
  Native Prometheus uses HTTPS Basic Auth; a registered read gateway may use bearer auth. Neither
  means an expiry date is known. Root/unseal/CA private material stays out of application mounts.
  Each local connector has a distinct generated credential. Native Prometheus Basic Auth itself
  has no label-level tenant authorization: local tenant isolation is enforced by MCP registration,
  fixed selectors, RLS and response normalization. Staging must review tenant-isolated upstream
  instances or a trusted tenant-aware read gateway; a shared Basic account is not upstream RLS.
- GET only; query/query_range/buildinfo allowlist; exact PromQL/template/timeout/limit. All DNS
  answers must match registration, then numeric address is pinned with TLS hostname and explicit
  CA verification. No proxy environment, redirect, compression or arbitrary endpoint dispatch.
- Range≤7days, bounded adaptive step≥15s,≤121 points per series,≤16 series,≤64KiB JSON. Engine
  `limit=17` detects overflow. Existing MCP response limit1–100 returns `truncated`; there is no
  unbounded cursor fetch. HTTP phases0.5s, request2s, async budget2.5s; read1 checks absolute body
  deadline even for drip feeds. The shared4-thread admission stays occupied until a timed-out
  DNS/header operation actually finishes. Breaker uses persisted failure/open state, no fixture fallback.
- Schema0020 preserves schema0019 tables/constraints/receipts and adds immutable bounded mapping
  JSON. Prometheus ingress is forbidden at contract and DB boundaries. Readers cannot mutate
  config. The tenant-bound has_binding function has no PUBLIC execute, only workflow/domain use.
  Configured sources fail closed at write preconditions; synthetic monitoring cannot authorize
  mutations for them. External write/native idempotency capabilities remain false.
- New app and fixture images use separate tags/digests. MVP isolation, source/static/contract/UI,
  actual-secret scans, dependency/image audits and preservation of all253 ASVS inherited fields
  are measured under evidence/f19. Earlier evidence is historical and is not overwritten.

## Limits and staging handoff

The local lab is an actual pinned Prometheus3.16.0 with HTTPS/basic auth, synthetic exporter,
real manager/DB/MCP and a separate HTTPS error server. It is never an authorized customer source.
Staging completion requires an explicitly approved endpoint and exact tenant mapping, least
privilege credential, CA/address policy, metric semantic/target review, actual version and redacted
MCP/UI smoke. Network firewall enforcement, production credential issuance/rotation and independent
deployment review remain F23 gates. Operator changes to scope/dataset/targets/auth require a new
connector identity; CA/address rotation remains a trusted operational policy change, not model input.

Primary protocol references: [query API](https://prometheus.io/docs/prometheus/latest/querying/api/)
and [native TLS/Basic Auth](https://prometheus.io/docs/prometheus/latest/configuration/https/).
