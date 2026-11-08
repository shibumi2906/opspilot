# F20 Jira sandbox preparation

2026-11-08; base 830ef61. Preparation only; F20 blocked on available authorized sandbox.

Discovery found no Jira/Atlassian environment or dotenv keys, no matching local
credential filenames under `.tools`, and no connected Atlassian tools. Marketplace
Atlassian is available but not installed. No site was guessed, no project was
selected from a working Jira account, and no vendor requests were made.

Connect Atlassian through the app to enable read-only sandbox discovery, or provision
an ignored local sandbox configuration and a tenant-scoped manager credential using
the existing secret workflow. Never paste credentials into chat. A plugin connection
alone does not provision the application's manager-backed REST credential.

Before any POST, independently confirm dedicated non-production site ownership,
exact project ID, allowed issue type and create-field metadata, Browse/Create/Add
Comments permissions, credential scope and approved test side effects. Project names
containing “sandbox” do not establish isolation. Do not create a paid sandbox/trial.

The offline `jira_payload.py` helper accepts trusted mapping only, emits a fixed
field allowlist and literal-text ADF, and binds site/project/type/version/outbound
bytes to a digest. The operation property is correlation metadata, not uniqueness.
It is deliberately unregistered pending the following implementation gates:

1. Immutable mapping enrollment, exact manager ACL and pinned bounded HTTPS transport.
2. Card/grant binding of destination, fields, marker, payload digest and mapping version.
3. Durable dispatch_started commit before networking; a single dispatch attempt.
4. Timeout/crash/429/5xx after dispatch => unknown, never automatic write retry.
5. Independent exact issue/comment reads; scoped reconciliation, zero matches stay
   unknown, multiple matches need attention; attach late responses to the same receipt.
6. Separate comment approval with exact issue destination; tenant and actor fences.
7. Simulator lost response/denial/rate-limit/duplicates and security/redaction tests.
8. Authorized sandbox reject=0, approve=exact issue, separate comment, replay=0 new
   objects, redacted receipts and audit/MCP/UI evidence. No live fault retries.

REST reference checked on 2026-11-08:
[Jira REST v3 issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
Payload preparation is not evidence of transport, authorization or full F20 acceptance.
ASVS SEC-03/09 and common SEC-01/10 remain open; protected backlog unchanged.
