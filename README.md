# OpsPilot Full

OpsPilot investigates operational incidents, links findings to evidence, and builds
action plans for human review. Authorized changes require explicit approval of the
proposed action. Durable workers preserve progress through restarts and record
execution results for verification and audit.

**Status as of 14 November 2026 — working Full Core with locally verified pilot
recovery. Pilot release acceptance is still open.** Remaining work includes the
production Jira connector and reconciliation path, external integration checks,
human evaluation review, remote CI, and deployment acceptance on an agreed target.

## Available functionality

- **Incident investigation.** Resolve the customer and integration, read operational
  evidence and knowledge articles, identify contradictions, request clarification,
  and produce reports with evidence references.
- **Human-controlled actions.** Create local tickets, add ticket comments, and send
  internal inbox notifications. Plans support dependencies, separate approval
  waves, rejection, cancellation, and partial execution.
- **Execution controls.** Immutable action revisions, approval expiry, signed
  execution grants, fresh precondition checks, revocation, and tenant/object scope
  checks bind approval to the authorized operation.
- **Durable processing.** PostgreSQL stores jobs, checkpoints, events, and operation
  results. Independent workers use leases and fencing to coordinate execution and
  recover interrupted work.
- **Identity and workspace.** OIDC sign-in, tenant memberships and roles,
  investigation history, approval views, inbox, administration, authenticated SSE
  updates, and reconnect/replay.
- **Operations and governance.** Scoped Redis caching, durable usage and cost
  accounting, request and concurrency limits, retention/export controls, audit
  history, protected telemetry, and operator diagnostics.
- **Integration platform.** Signed durable observation ingress and a scoped
  Prometheus read connector, including evidence from temporary AWS staging.
- **Model modes.** Scripted mode supports reproducible local checks. Real-provider
  mode has separate evaluation evidence and explicit usage budgets.

Local ticket and inbox operations use OpsPilot's database. Jira integration
currently has payload preparation, exact-match verification rules, and a durable
local dispatch/reconciliation simulator. Connecting Jira to the application
execution path remains part of F20.

## Verification and remaining acceptance

| Area | Verified result | Remaining work |
| --- | --- | --- |
| F01–F19 | Core implementation and Prometheus staging acceptance recorded | Preserve stage-specific limits when choosing a pilot target |
| F20 — Jira | 27 local payload, verification, preflight, and simulator tests passed | Integrate trusted mappings, grants, bounded transport, PostgreSQL dispatch receipts and reconciliation into the runtime; verify authorized sandbox writes and read-back |
| F21 — resilience | Local concurrency, fault, recovery, load, and 30-minute soak evidence recorded | Exercise the completed F20 dispatch/reconciliation boundaries and verify the release environment |
| F22 — evaluations | 50/50 Full scripted cases; all 90 scheduled real results recorded, with 78 passes and 12 failed records; successful diagnostic repeats cover all 12 historical failures | Owner judgments for individual claims and hypotheses; successful remote CI on the intended Full commit; dependent integration and release gates |
| F23 — pilot preparation | Local Compose/runbook, browser TLS/OIDC/MFA, encrypted backup, separate database restore, rollback, and recovered-worker checks passed | Agreed pilot host/domain/issuer, target security controls, off-host recovery, full target RTO, and deployment acceptance |
| F24 — release | Specification and implementation tracker available | Final release, traceability, and acceptance after outstanding gates close |

The real evaluation's original 78/90 result and diagnostic repeats are recorded
separately. The holdout set has been inspected. Full Pilot and complete ASVS L2
acceptance remain **NOT_MET**.

### Latest local security and recovery evidence

The separately built manager image uses OpenBao 2.7.2 with
`golang.org/x/net 0.62.0`. The 14 November scan reports **0 HIGH/CRITICAL** findings.
The new image passed application approval and recovery checks in an isolated lab.
Existing environments require their own controlled rollout to adopt this image.
[Manager scan and image identity](docs/full/evidence/f23/manager-nov14/checks.json)

Local browser checks cover TLS peer validation, OIDC login, TOTP MFA, a separate
approver, and session revocation. Encrypted backup/restore preserves counts and
hashes across 57 tables, a pending interrupt, and a committed operation receipt.
On the restored synthetic instance, replay creates zero additional tickets and
approval resumes the pending run with exactly one new ticket.
[TLS and browser evidence](docs/full/evidence/f23/tls-r3/browser.json) ·
[Latest restore evidence](docs/full/evidence/f23/opspilot-full-test-f23-r8/recovery.json)

The latest measured interval from private-network preparation through restore and
worker verification is **22.86 seconds**, with PostgreSQL and the manager already
running. Full recovery time on the selected pilot environment still needs measurement.
[Measured recovery scope](docs/full/evidence/f23/opspilot-full-test-f23-r8/recovery-worker.json)

## Local development

The Full checkout uses branch `codex/opspilot-full` and Compose project
`opspilot-full`. Existing local development uses
`compose.full.yaml`, `compose.full.f17-local.yaml`, and
`compose.full.f18-local.yaml` together. Test labs use separate projects and data.

Follow [START-HERE.md](START-HERE.md) for the prepared workspace, credentials,
manager token refresh, preserved database volume selection, and startup commands.
The existing development database remains on schema `0019_adapters`; later
test schemas and the new manager image have separate evidence.

| Development service | Address |
| --- | --- |
| Web workspace | http://127.0.0.1:8091 |
| API health | http://127.0.0.1:8011/health |
| Local OIDC provider | http://127.0.0.1:8181 |

These addresses belong to the local development profile. TLS verification uses
a separate native TLS lab. Local secrets, private keys, and backups are stored
in ignored files.

## Documentation

- [Implementation tracker](docs/full-version-status.md)
- [Full specification](OpsPilot_Full_Project_Specification.md)
- [F20 Jira implementation and access gaps](docs/full/f20-jira-preparation.md)
- [F21 resilience measurements](docs/full/evidence/f21/README.md)
- [F22 original real results and diagnostic review](docs/full/evidence/f22/continuation/review-final/README.md)
- [F23 pilot runbook](docs/full/f23-pilot-runbook.md)
- [Latest local checks and limitations](docs/full/evidence/f23/local-followup.md)
- [Portfolio MVP and its quickstart](https://github.com/shibumi2906/opspilot/tree/opspilot-portfolio-mvp-v1.0)
