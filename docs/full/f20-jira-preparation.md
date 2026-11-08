# F20 Jira sandbox preparation

2026-11-08; base a9e50bf (F19 830ef61). Preparation only; F20 remains blocked on complete API scopes and remaining implementation gates.

Historical initial discovery found no Jira/Atlassian environment or dotenv keys, no matching local
credential filenames under `.tools`, and no connected Atlassian tools. Marketplace
Atlassian is available but not installed. No site was guessed, no project was
selected from a working Jira account, and no vendor requests were made.

## Current access evidence

The owner created `https://makegrigorev.atlassian.net`, dedicated `OpsPilot Test`
project `KAN`, and showed its Free subscription with no payment method. No Codex
Atlassian plugin is needed. The owner saved a scoped token locally; the original
Markdown was moved by explicit request into ignored `.tools/f20-private`. A separate
normalized local credential removes Markdown escaping; no credential values are logged.

[Read-only preflight](evidence/f20/jira-preflight.json) proves authentication and
BROWSE_PROJECTS/CREATE_ISSUES/ADD_COMMENTS in KAN (HTTP200). GET project/issue/myself
returned HTTP401 with the provider category `scope does not match`, not evidence of
an invalid token. The initial list of17 scopes supplied by the agent was incomplete.
The full official per-endpoint dependency sets include12 additional scopes. This
mistake is recorded; no provider permission or endpoint safety check was bypassed.
[Gap](evidence/f20/scope-gap.json), [official endpoint metadata](evidence/f20/vendor-required-scopes.json),
[complete29-scope list](f20-jira-required-scopes.txt). Even creation requires the
vendor-declared write:attachment scope when no attachment is sent. This does not
authorize OpsPilot attachment operations. Runtime will still allow only fixed issue/
comment endpoints in KAN; broad account rights alone do not establish that boundary.
Do not replace the scoped credential with an unrestricted token merely to pass tests.

A replacement token must be saved locally through the same workflow (never in chat).
Atlassian token settings cannot be altered using this Jira application credential.
Browser automation remains unavailable with `failed to write kernel assets`; no
account/security UI actions were automated. No new paid resources/subscriptions.

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
5. Wire the implemented pure issue/comment match rules to independent reads and scoped reconciliation; zero matches stay
   unknown, multiple matches need attention; attach late responses to the same receipt.
6. Separate comment approval with exact issue destination; tenant and actor fences.
7. Simulator lost response/denial/rate-limit/duplicates and security/redaction tests.
8. Authorized sandbox reject=0, approve=exact issue, separate comment, replay=0 new
   objects, redacted receipts and audit/MCP/UI evidence. No live fault retries.

REST reference checked on 2026-11-08:
[Jira REST v3 issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
Payload preparation is not evidence of transport, authorization or full F20 acceptance.
ASVS SEC-03/09 and common SEC-01/10 remain open; protected backlog unchanged.


## Scoped checks and limits

`jira_verification.py` checks exact project/type/summary/ADF/operation property; only
paragraph attrs.localId is explicitly normalized away. Prepared marker rebinding is
rejected. Zero/incomplete search stays unknown; multiple or mismatched matches need
attention. Comment destination must still be independently checked by the future caller.
There is no retry capability in these pure rules. They are not a durable reconciler.

Ruff/format pass; mypy2 modules pass; scoped pytest21 pass:
`python -m pytest tests/unit/test_jira_verification.py tests/unit/test_jira_preflight.py tests/test_f20_jira_payload.py --basetemp=.tools/f20-unit-r2 -q`.
The first targeted attempt had3 temp-directory permission errors; a workspace-local
basetemp fixed them without changing assertions. Two broader host-unit attempts were
interrupted after26 completed tests, stalled at the inherited
`test_transport_timeouts_keep_actual_threads_bounded`; they are not accepted results.
No baseline tests were edited or skipped to claim full acceptance.

Existing MVP isolation gate passed after starting Docker Desktop with elevated tool
access:184 files/env, main/HEAD, images, volume metadata and read-only volume content.
No images were built, no migrations/seed/dev updates performed. Full remains0019.
No upstream Jira POST/PUT/DELETE, no paid calls, remote CI or push. Protected253 ASVS
backlog rows are unchanged. Complete SEC-03/09 and SEC-01/10 stage gates remain open.
