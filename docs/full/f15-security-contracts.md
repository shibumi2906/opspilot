# F15 — resource and cache security contracts

Scope: Full only, base F14 `be246d7`, schema `0016_governance`; MVP remains separate.
No new write tools, graph edges, connector URLs, model default, paid calls or future stage.
State/DTO1, graph v1/v2 and checkpoint SDK contracts remain compatible. Existing consent and
Core/MCP fresh precondition/verification authority never depend on Redis.

## Durable authority and admission

PostgreSQL owns initial run/job insertion, resource counters, immutable attempt identities,
leases and model-price snapshots. Initial enqueue remains atomic, and terminal SDK/import records do not occupy active capacity.
Reactivation of a terminal run is gated too; actor admission now spans
all of that actor's tenants. Local defaults:8 active runs/actor,64/tenant,128/global. The isolated
bulk regression profile explicitly uses the former1000/5000/10000 ceilings. Migration imports
are a trusted administrative operation; runtime callers cannot exceed those hard ceilings.

Worker admission serializes against live database-time leases:4/global,2/tenant,2/actor.
Among configured tenants with eligible pending work, the least recently admitted tenant gets
the next turn; FIFO applies within a tenant. Considering the worker's configured tenant set
prevents an unserved tenant from blocking other workers indefinitely. A targeted internal
run claim may omit turn rotation; all shared capacity caps still apply. Human waiting releases
a worker lease while its active-run reservation remains. Expiry/reaping transfers ownership;
Redis deletion or restart never grants a new worker slot.

Every research read, round and provider attempt reserves before dispatch under the current
fence. Reservation/settlement use fixed-search-path SECURITY DEFINER functions, PUBLIC execute
revoked and narrow role grants. Runtime roles cannot read/write the underlying resource ledgers
or policy/price tables directly. Tenant ledgers use FORCE RLS. SQL validates all run-budget
fields and ceilings; malformed/missing budgets cannot turn into unlimited dispatch.

Per run:6 rounds,15 research reads,10 provider attempts,30000 input+output tokens and120 active
seconds, bounded further by the persisted run limits. Verification uses its separate existing
3-read/action reserve; exhausting research tokens does not prohibit checking an executed effect.
Retry and replay create new charged attempts; Redis hits still consume the research/source
request quota. Started/unknown provider rows retain held tokens/spend and conservative timeout
active time. A worker crash before checkpoint therefore cannot refund a request. A stale epoch
cannot settle it. Known usage may release only the unused reservation, including invalid model
output with reported usage. Actual usage is never clamped down to the reservation.

Provider-hour limits are shared across runs/tenants:200 attempts and600000 tokens/actor,
1000/3000000 per tenant,3000/9000000 globally. Known plus held USD limits are5/actor,20/tenant,
100/global per hour, with a0.50/run known-price cap. The hourly external-provider windows exclude
the scripted fixture provider, which makes no API request; per-run orchestration limits still
apply. Rolling windows expire by database time; lifetime run counters and uncertain reservations
remain durable. Legacy run counters are conservatively backfilled; historical model spend is
partial rather than reconstructed using today's prices.

The request reservation uses the exact rendered payload's UTF8 byte length as a conservative
visible-token bound,4000 maximum output tokens and2048 overhead margin. It is local admission,
not an invoice guarantee. Unexpected provider overuse remains recorded and blocks subsequent
work. CI uses scripted fixtures or explicitly labelled HTTPX mock transports, without paid calls.

## Source cache and degradation

Redis is private, password/ACL protected, non-root, read-only filesystem,64MiB cache memory,
96MiB container memory,64 clients, no AOF/snapshot and no published host port. Local dev and
regression have separate ignored passwords and integrity keys; the native TLS lab has another
independent set. Hardened Redis requires `rediss`, trusted CA and hostname verification, with
no URL credential/query overrides. Only needed key-prefixed commands are allowed.

The cache key binds database namespace UUID, tenant, actor, customer, tool, canonical arguments,
source generation and synthetic scenario/version clock. Status/customer TTL15s; retrieval60s.
Every domain-source/connector-control mutation advances a transactional database generation.
The version is a namespace baseline plus the sum of committed per-object versions, with
persistent object tombstones. Independent source writes do not lock one shared tenant row;
out-of-order commits still advance the visible sum. Owner moves invalidate both tenants and
no-op updates need no invalidation. Rotate the namespace atomically before future metadata
compaction; do not reset the sum under an existing namespace. The aggregate scans one small
metadata row/source object under the existing DB statement deadline; production-scale load
and compaction remain F17/F21 work, without a claimed performance SLO.
Old values cannot be rediscovered under the new generation. Every hit follows live user/role
and object authorization. Cached envelopes have an independent HMAC, matching scope, bounded
size and signed creation/expiry; the operation DTO is validated again before use. Redis-side
length checking prevents an oversized poisoned value from being transferred to the client.

Only customer lookup, status/events and incident/document retrieval are cacheable. Credentials,
permissions/sessions, approvals, grants, preconditions, tickets/notification/comment verification
and writes are excluded. Errors are never cached as success. Source observed_at is retained.
Redis source-cache hits are unrelated to provider prompt-cache tokens and never invent model
cached-token savings.

Source admission always charges PostgreSQL actor/tenant/global fixed-minute counters before
cache access or direct work:600/1800/6000. Redis has an additional fast duplicate actor limiter;
eviction/restart cannot reset the database counters. Redis operations have200ms socket and250ms
outer deadlines, no retries,8 pooled connections and a5s local circuit interval. On failure,
only already-admitted bounded direct reads proceed. DB/authorization failure cannot fall back
to Redis permissions. Write authorization and quotas remain fail-closed during Redis outage.

## Pricing and public projection

The versioned USD catalogue records source, project effective date, verification date and expiry.
The30 October2026 standard snapshot expires29 November2026; model choice stays explicitly
configured. Reviewed aliases/snapshots: `gpt-5-mini` / `gpt-5-mini-2025-08-07` and
`gpt-5.4-mini` / `gpt-5.4-mini-2026-03-17`. These are catalogue entries, not a model recommendation.

Prices per million input/cached-input/output tokens are0.25/0.025/2.00 and0.75/0.075/4.50.
Sources: [GPT-5 Mini](https://developers.openai.com/api/docs/models/gpt-5-mini),
[GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
Responses explicitly requests `service_tier=default`; unexpected tiers or cache-write billing
stay unpriced. The actual served model must match reviewed rates before settlement can use
that price snapshot. [Responses service tiers](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

Uncached input, cached input and output are priced separately using NUMERIC arithmetic. Attempts
keep the dispatch price snapshot, so later catalogue changes cannot reprice history. Unknown,
expired or unsupported prices/usage produce null total cost and a partial state; known subtotal
and held reservations remain separate. Reported cached tokens are not subtracted twice from
input. UI labels scripted zero API cost distinctly and never renders unknown total as zero;
positive values below one micro-dollar render as `<0.000001`. Catalogue cost is local list-price
accounting, not reconciliation of taxes, discounts or a provider invoice.

## Verification and residual scope

Required gates: actual PostgreSQL/Redis concurrency/scope/poisoning/invalidation/disable tests;
crash after provider reservation but before checkpoint; real Redis stop/recreate with unchanged
PG attempts/held tokens; actor capacity across tenants; unknown/expired/other-tier pricing;
full existing backend/browser/process/eval/security regressions; native TLS Redis CA/hostname/
password/plaintext negatives; preserved-data local Full upgrade and final MVP fingerprint.

ASVS SEC-07 plus SEC-01/10 change review applies. All253 requirement IDs, levels, baseline
assessments, accountable owners and owner-N/A fields are preserved. Scoped F15 evidence does
not close whole-application norms. Production secret management, retention, load/soak, real
provider billing reconciliation and deployment remain their accountable future gates. Full
ASVS L2 remains NOT_MET. Local Docker/WSL upgrade was recommended after observing an old host
runtime; no host update or production-host security acceptance is implied by these app gates.
