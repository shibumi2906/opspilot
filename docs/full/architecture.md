# OpsPilot Full — architecture

Current portfolio architecture, 20 November 2026. The [F01 baseline](architecture-f01.md)
is retained separately; its stage limitations are historical.
[Portfolio scope](portfolio-completion.md) · [Implementation history](../full-version-status.md)

## Boundaries

The React workspace talks to a FastAPI backend-for-frontend. OIDC establishes a
server-side session; tenant memberships and roles come from authoritative storage.
The browser submits requests and decisions. It does not hold provider tokens or
decide which domain writes are authorized.

PostgreSQL owns durable jobs, workflow state, action revisions, approvals, checkpoints,
events and receipts. Separate workers execute LangGraph under per-run leases and
ownership epochs. Database and MCP fences reject stale ownership at commit boundaries.

The model adapter selects bounded reads and proposes typed actions. Core code owns
validation, policy, budget, approval, signing, execution and verification. The default
showcase selects a scripted provider so its behavior is repeatable.

## Request-to-effect path

1. API authenticates the actor, selects the tenant and validates the request.
2. A transaction commits the run, start job and associated public events.
3. A worker claims fenced ownership, reads evidence through MCP and saves a checkpoint.
4. Core validates a proposed action and persists its immutable revision and payload hash.
5. An authorized reviewer approves that exact revision before its expiry.
6. A durable resume job rechecks actor/tenant permissions, cancellation and preconditions.
7. A scoped signed grant authorizes the exact MCP tool call.
8. The effect and receipt are recorded; independent verification determines the result.

Multi-action plans add dependencies, approval waves and per-action outcomes.
Authenticated SSE exposes bounded progress/replay; authoritative snapshots remain
the recovery source for reconnecting clients.

## Data and trust boundaries

| Boundary | Responsibility |
|---|---|
| API / identity store | Cookie session, CSRF/origin checks, memberships and response projection |
| Workflow PostgreSQL role | Jobs, graph state, approvals, checkpoints and durable resource reservations |
| Private MCP server | Typed tool registry, grant validation and bounded domain effects |
| Tenant-scoped database sessions | Row-level security plus explicit tenant/object/actor checks |
| Redis | Scoped cache; durable business truth and operation receipts remain in PostgreSQL |
| OpenBao manager | Scoped service access and managed signing-key lifecycle used by the pilot |
| Telemetry collector | Bounded structured events, protected journal and separate seal state |
| OIDC provider | Password/TOTP authentication and identity session lifecycle |

The integration registry accepts trusted enrollment, not model-supplied destinations.
Observation ingress is signed and durable. Prometheus is a read connector. Enrolled
Jira issue/comment writes use a durable dispatch-started receipt and one network
attempt. A timeout or crash can leave an explicit unknown outcome; reconciliation
reads existing results and never blindly retries the write.

## Deployment profiles

- **Preserved main Full development:** project opspilot-full, schema0019_adapters.
- **Recorded local TLS pilot:** opspilot-full-test-f23-recovery4, test schema0023,
  separate private/edge/management networks and loopback HTTPS listeners.
- **Ephemeral CI:** a separately initialized GitHub-hosted scripted stack; no model
  or Jira credentials are supplied.

The pilot runs pinned images with private service TLS, OIDC/TOTP and separate
operator/approver identities. It is a synthetic demonstrator. Production identity
onboarding, comprehensive secret lifecycle and host/off-host protections remain in
the [production-hardening assessment](../security/release-review-20261116/README.md).

## Recovery and operations

The [backup tool](../../scripts/full_backup.py) quiesces pilot writers, records a
logical database dump and five volume/config payloads, then resumes the recorded
service set. Each bundle is authenticated and encrypted; retention validates every
catalog entry before removing owned files. A durable pre-stop journal supports
interrupted-operation recovery. Offline verification refuses existing Docker targets.

The whole-pilot rehearsal matched59 table hashes and measured63.88 seconds on the
recorded host with preloaded images. It included recovered IdP/manager and approval
behavior. [Evidence and limits](evidence/f23/local-pilot-20261116/README.md)

## Design records

- [Tenant isolation](adr/004-tenant-isolation.md)
- [Graph versioning](adr/002-graph-versioning.md)
- [Permissions](adr/003-permissions.md)
- [Durable jobs](durable-jobs.md)
- [Execution fencing](execution-fencing.md)
- [Checkpoint adapter](adr/006-fenced-checkpoint-adapter.md)
- [Jira dispatch and reconciliation](f20-jira-runtime.md)
- [Operational backups](f23-operational-backups.md)
