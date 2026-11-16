# F20 security change review

Scope: Jira issue/comment runtime, tenant-bound trusted enrollment, one-attempt
receipts, independent verification and operator reconciliation. This review adds
implementation/evidence references; it does not close whole ASVS requirements.
All 253 protected backlog records, owners, baseline and N/A fields are preserved.

## Authorization and transport

The model cannot select credentials, origins, project mappings or arbitrary REST
paths. Trusted binding resolution checks tenant, connector, customer, mapping
version, site, project and issue type. The manager record independently binds its
credential to the tenant/connector/site/project. Worker mounts do not contain Jira
credentials; MCP retrieves only the configured connector path under its exact ACL.

Service context, current revision, approver, payload hash, expiry, tool, execution
epoch and signed grant are checked before mutation. PostgreSQL RLS and fenced
receipt triggers provide an additional boundary. A separately approved comment
binds its parent issue. Mutable connector configuration is checked against the
approved immutable mapping and cannot silently redirect an existing approval.

The HTTPS transport has fixed routes, public numeric-address allowlists, complete
DNS answer validation, numeric address pinning and hostname/CA validation. It does
not accept model-provided URLs, proxies or redirects. Header injection, unknown
routes, malformed IDs and oversized requests are rejected before socket use.

The one-attempt record is committed before Jira dispatch. Neither timeout, missing
readback nor an absent search result permits another POST. Provider IDs survive
subsequent GET failures. Verification checks exact business fields and operation
properties; reconciliation detects late duplicate markers and fails to attention.
This is not a claim of Jira-native exactly-once delivery or native idempotency.

## ASVS contribution references

| Backlog scope | Changed implementation | Evidence and remaining boundary |
| --- | --- | --- |
| SEC-03, 2.1/2.2/2.3 | Strict Jira DTOs, immutable revisions, dependency plans, exact grants, durable one-attempt record | Native boundary tests cover tampering/replay, permission/rate denial, lost/slow replies, read failure, mismatch and late duplicates. Whole validation/business-logic review remains open. |
| SEC-03, 8.1/8.2/8.3/8.4 | Owning operator and tenant reconciliation, recent authentication, MCP authorization, RLS/fencing | Actual API decisions and PostgreSQL/MCP checks; foreign/changed grant claims fail closed. Whole authorization matrix and deployment review remain open. |
| SEC-03, 9.1/9.2 | Exact service context and independent signed grants, manager-backed signing keys | Existing negative signature/claim tests and Jira boundary tests. No blanket JWT/whole-requirement acceptance. |
| SEC-09, 13.2.1–13.2.5 | Fixed HTTPS routes, trusted DNS/address/CA scope, connector-specific manager credentials | Transport negative unit tests and authorized sandbox receipts. Upstream least privilege remains constrained to the owner's KAN test project. |
| SEC-01/10 common gates | Independent Full resources, scripted checks, preserved evidence, artifact/secret checks | Backend results and failures are listed separately; no whole L2/release claim. Final image scans and release-SHA CI remain required. |

Code: `src/opspilot/mcp_server/services/jira.py`, `integrations/jira_transport.py`,
`integrations/jira_registry.py`, `api/routes_jira.py`, `runtime/plans.py`,
`security/grants.py`, and migrations0022/0023.
[Runtime runbook](f20-jira-runtime.md), [measured evidence](evidence/f20/README.md).

Real sandbox attempts include failed and unknown comment attempts. Their reports
are retained and they were not resent. The successful existing-receipt replay
report records zero new POSTs and no duplicate markers; it does not reclassify
earlier unknown attempts as successful or safe to retry.
