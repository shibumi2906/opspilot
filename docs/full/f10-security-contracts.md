# F10 local operations security contracts

Scope: three local single-action tools; no DAG, connector or new UI. Parent F09 278d92d.
Before schema changes: every operation binds tenant, actor, tool, exact typed arguments,
revision, approval and transient independent signed grant. MCP rechecks persisted authority.
Comment targets must be an existing same-tenant ticket belonging to the approved customer. The actor must own its originating run or hold a live approver/auditor role.
Notification recipients must be enabled existing tenant members; membership is locked through commit.
No email, webhook, URL fetch or external delivery is performed. Internal inbox persistence is the effect.

SEC-06: body, evidence references, ticket/customer/recipient IDs are tenant confidential;
recipient IDs are personal data. Payloads are bounded plain text, never executable HTML/Markdown.
DTOs expose only approved fields, origin operation, generated ID/time; no identity provider subject,
credentials, service context, grant or private workflow state. Events/audit keep their existing
identifier/status allowlist and never copy bodies. Do not put secrets in approved business content.
Tenant retention/export/delete and anti-replay tombstones remain F17; encrypted storage and backup
retention remain F23. No premature control closure or complete L2 assertion.

SEC-08: JSON-only strict DTO output, no HTML response or active URLs; inherited security headers,
no-store and CSP apply. The minimal approval card renders bodies as React text nodes, never innerHTML or active URLs; the future F14 inbox must preserve that rule.
Reads require object authorization: run owner or approver/auditor; inbox recipient may read own item.
Foreign objects return the same not-found response. No bulk export endpoint is introduced.

SEC-03: transaction locks fence, immutable action and approval, current roles and live recipient;
grant consumption, domain row and receipt commit together. Replay returns the same object.
Independent read verification compares every approved field plus origin, object ID and timestamp.
Missing read => unknown; mismatching read => partial, never verified. Lost response recovers receipt.
