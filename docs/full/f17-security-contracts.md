# F17 lifecycle and managed signing contracts

Scope: local Full Core, base `6330f32`, schema `0018_lifecycle`; graph v1/v2,
DTO/state 1 and checkpoint SDK 9 remain pinned. No F18 connector work or Pilot release.
Full ASVS L2 remains **NOT_MET**. Historical evidence is not refreshed by assertion.

## Trust boundaries and abuse cases (SEC-01/04/05/06)

The lifecycle CLI is an explicit administrative workflow, never an agent tool or timer.
It requires the dedicated migration connection **and** an active administrator membership
in the selected tenant. Tenant UUID supplied at the CLI is not sufficient authority.
Preview and apply both recheck eligibility; apply requires an exact preview digest bound to
tenant, actor, policy and the bounded candidate set. A stale digest fails before erasure.
There is no request/body/evidence/credential in preview, export or lifecycle audit records.
Exports use a positive metadata allowlist and a 100-row export bound. Existing browser exports keep
live session/RBAC/tenant checks, no-store, nosniff, size bounds and audit from F14.

Runtime workflow/domain transactions and checkpoint transactions take a shared maintenance
lock. Administrative compaction takes the exclusive counterpart before selecting candidates;
runtime operations therefore cannot cross eligibility inspection and erasure. A five-second operation deadline, a 20-run default batch (maximum100), and SQL/lock/idle deadlines bound the operation; a lock failure rolls back everything and requires a new
preview. This is a small-Core batch maintenance design, not an online large-scale purge SLA.

The new internal maintenance-lock query does not add a redundant DB span to every
transaction; business SQL and its failures remain traced. Core regression exposed trace
batch loss under collector admission contention. An explicit authenticated receiver header
now identifies rejection before any journal work was submitted. Only such trace batches
may retry, at most three attempts with50/100ms backoff and the existing0.3-second HTTP
phase timeout. Unknown HTTP outcomes, integrity failures and post-admission timeouts are
not retried, preventing duplicate accepted batches. Queue/concurrency/storage bounds,
native mTLS, redaction and full journal-chain verification remain enforced. Telemetry is
bounded operational evidence; durable job/audit/receipt ledgers remain authoritative.

Only terminal completed/cancelled/failed runs can qualify. Pending approvals, unknown actions
or slots, pending/running jobs and live leases exclude the whole run. Needs-attention and
reconciling are excluded even if someone makes their timestamps old. Default project periods
are evidence/tool payload/checkpoint 30 days, history/request/action content 90 days, and
body-free event/audit 365 days. These are project settings, not legal retention periods.
Policy is strict, ordered, bounded, supplied per invocation and reversible without mutating
the running configuration. Increasing retention cannot reconstruct content already erased.

Identity/hash ledgers are retained indefinitely, exceeding the project 365-day minimum and
all permitted command/grant replay windows. Root run/client-request IDs, revision hashes,
logical action identities, command IDs and domain result references remain reserved. Runtime
cannot change tombstones or reopen an erased run/job/action/grant/lease. Immutable-revision
and plan triggers permit only exact content erasure by the administrative login after the
appropriate tombstone has been inserted, in the same transaction. No trigger is disabled.
SSE sequence stays monotonic when old replay rows are compacted, preserving reset semantics.
Business tickets/comments/inbox records are independent retained business objects; erasing
workflow evidence does not delete their committed effects or authorize a replacement effect.

Tenant/user account deletion is separate from timer retention: preview eligibility and
backup boundaries first, revoke access through the existing administrator workflow, retain
anti-replay identities, and perform any approved business-record purge as a separately reviewed
operation. This stage does not silently cascade deletion through customer/business objects.

## Secrets manager and recovery

OpenBao **2.7.2+opspilot-f17.1**, pinned build inputs and exact runtime image ID in evidence, runs outside dev mode with native
verified TLS, non-root UID 100, read-only root, dropped capabilities, memory/PID bounds, encrypted
Raft storage, a separate protected audit volume and 2-of-3 unseal shares. Only loopback 18200 is
published for the local operator; applications use the private manager network. No root token,
unseal share, CA private key or server private key is mounted into an application container.
The failed sealed first candidate is preserved; it never held application secrets.

The provider-neutral grant-key interface selects the manager explicitly. Manager failure,
denial, TLS failure, oversized/invalid response, missing version or revoked key fails closed;
the local file adapter is never used as a manager fallback. Paths and origins are registered,
redirects/proxy environment are disabled, requests have a 2-second timeout and 16-KiB bound.
Private Ed25519 material exists only in the worker's transient signing memory; never in grants,
checkpoints, model context, exports, traces or audit payloads. MCP can resolve public keys only.
Worker credentials cannot mutate keys, active configuration or ACLs. Tenant probe credentials
read only their own namespace and cannot read grant keys or another tenant's namespace.
Local per-service access tokens expire after at most one hour, are non-renewable, and are
explicitly replaced by the operator; they are not manager root credentials.

Rotation publishes verification overlap, creates a new immutable private version and then
switches the active reference. In-flight signatures retain the old key identity for the
maximum 60-second grant lifetime. Compromise removes the old verification entry and revokes
affected service access immediately; a still-unexpired signature is then refused. Rollback
switches only a reviewed active reference. Reuse of a compromised key is a recovery decision,
not automatic fallback. The drill uses synthetic keys and verifies both overlap and refusal.

Manager backup is barrier-encrypted Raft snapshot plus a Fernet envelope. The independent
envelope key and unseal shares are in ignored recovery storage, separate from the backup.
The drill restores into another fresh instance and verifies original key identity after a
restart and original threshold unseal. A snapshot cannot erase the independent deletion
ledger of a newer application backup: an application restore must reapply post-backup erasures
and tombstones before enabling any writes. F23 owns deployment storage encryption, off-host
backup retention and a complete application restore/rollback drill.

Manager audit uses declarative configuration with HMAC-redacted secret fields. Raw audit
data and private recovery material stay local. The sentinel drill checks actual audit bytes;
application telemetry retains the protected F16 positive schema. Audit/log rotation must
retain forensic continuity; never delete a journal to obtain healthy diagnostics.

## Supply chain and patch policy (SEC-10)

Keep lockfiles, exact base images, scanner digest, scanner DB timestamps, raw package/OS/Go/JAR
results and CycloneDX inventory. Scan package and image layers; do not ignore applicable CVEs,
remove metadata, or count accepted risk as pass. Existing exact-image IdP component assessment
must be rerun against the current image and findings, not copied as fresh evidence.

F17 replaces the IdP's Debian runtime after new expat/zlib findings, retaining
Keycloak26.8.1 and security-fixed Java21 on Alpine with package metadata intact.
The Java probe compares the full version against21.0.13+9, including downstream
patch components, using the documented
[Runtime.Version ordering](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.Version.html).
It also checks the actual Guava bytes and default truststore. Runtime changes require
a fresh image scan and native TLS/MFA/browser verification before local rollout.

Project operational patch targets: critical actively exploited issues block promotion and
are triaged within one business day; other critical/high issues block promotion and target
remediation within 7 days; medium within 30 days; low within 90 days. The local operator owns
triage, updates the pinned dependency/image, reruns affected acceptance/security checks and
records the replacement artifact and findings. A deadline is not vulnerability acceptance.

The PostgreSQL16 runtime is16.15. The official
[version16 security table](https://www.postgresql.org/support/security/16/) and
[16.15 release notes](https://www.postgresql.org/docs/16/release-16-15.html) were reviewed
alongside the image scan. This source-built server needs an explicit version review
because an OS package scanner alone does not establish PostgreSQL server coverage.
The libc transition uses a fresh logical restore with rebuilt indexes; the original
physical volume and encrypted backup are preserved. See the measured restore evidence.

Official implementation references:
[OpenBao installation](https://openbao.org/docs/2.5.x/install/),
[KV v2](https://openbao.org/docs/secrets/kv/kv-v2/),
[Raft storage](https://openbao.org/docs/configuration/storage/raft/),
[declarative audit](https://openbao.org/docs/configuration/audit/).
