# F03 — local OIDC identity and sessions

Full-only Keycloak 26.2.5 is built as opspilot-full/oidc:f03 from digest
4883630ef9db14031cde3e60700c9a9a8eaf1b5c24db1589d6a2d43de38ba2a9.
Its dev H2 data uses the separate project oidcdata volume; only 127.0.0.1:8181 is published.
This start-dev issuer is for local synthetic use; pilot TLS/deployment remains F23.

## Trust and lifecycle

BFF Authorization Code Flow uses PKCE S256, random state, nonce and an HttpOnly browser-binding
cookie. Login attempts are server-side, expire after five minutes and are consumed by atomic DELETE
RETURNING. A replay/foreign binding cannot finish login. The callback URI comes only from APP_ORIGIN;
caller Host/next/tenant headers cannot change it. Discovery issuer and token/JWKS endpoints are pinned,
HTTP redirects are not followed, and ID tokens require RS256 signature, issuer, audience, exp, iat,
subject and nonce. Multiple audiences require the expected authorized party.

OIDC tokens are consumed in the BFF, never returned to browser storage/model/checkpoints. There is no
password grant or homemade JWT login. Local realm credentials are independent ignored .env secrets;
realm import uses environment placeholders, not committed passwords. Direct access grants/registration
are disabled. User identity is unique (issuer,subject); a successful login alone grants no membership.

The BFF issues a new random opaque session cookie on every login, revokes the old session to prevent
fixation and stores only the session token hash. Cookies are HttpOnly/SameSite=Lax/host-only, Secure
when APP_ORIGIN is HTTPS. Local HTTP is deliberate; it is not a pilot HTTPS profile. Sessions expire
using database time; logout revokes the server session and removes the cookie. Provider SSO is separate
from this application session; BFF logout does not claim IdP-wide single logout or token revocation.
No refresh tokens are stored. App session TTL defaults to eight hours.

Every request reloads session/memberships. Every mutation requires the exact configured Origin and
an HMAC-derived CSRF token available through same-origin /auth/me, kept only in JS memory. Selecting
another tenant checks current memberships, changes only the server session, clears pending browser
request state and reloads the workspace. The UI blocks overlapping identity mutations. No JWT, role
or arbitrary tenant supplied by a browser becomes authority.

## Roles and default policy

operator creates/reads own runs; approver reads/decides within tenant; auditor reads redacted tenant
runs; admin manages membership/configuration without implicit domain approval. F03 exposes only the
minimal login/tenant selector and role-aware approval controls; full admin UI is F14.
Self-approval is denied by default in Settings. The local Compose explicitly enables a labeled demo
exception for operator+approver; decisions store decided_by and self_approval_exception in the same
workflow transaction. A plain operator still cannot approve. The UI shows the acting user and roles.

IdentityStore uses a dedicated ops_identity login with an independent password. It has explicit
RLS gateway policies on global identity/session tables, no ownership, superuser or BYPASSRLS, and
no access to domain/checkpoint data. This trusted BFF role performs pre-tenant session lookup;
ordinary workflow/domain roles do not receive its credentials or global identity grants.
Migration 0004 creates the NOLOGIN role; the explicit bootstrap CLI sets its local secret and
provisions known synthetic OIDC subjects/memberships. No public bootstrap/provisioning route exists.

## Setup/checks

New Full installations use scripts/new-full-env.ps1, which now generates four additional independent
identity secrets. For an existing Full .env, generate missing values independently; do not copy MVP.
Build Full, run admin (Alembic), seed, then admin python -m opspilot.cli.bootstrap_identity before
starting API/web. Bootstrap prints no passwords. Synthetic usernames: demo, operator, approver,
auditor, admin, unassigned. Their local password is OIDC_DEMO_PASSWORD in the ignored Full .env.
demo has operator+approver in A/B; unassigned has none. Roles come from the application DB, not
unverified IdP role claims. The local issuer realm ID/subject mappings are deterministic fixtures.

Run powershell -NoProfile -File scripts/test-full-f03.ps1 for the stage gate. Tests use their own
OIDC hostname, project volume, exact origin http://web and opspilot_full_test database. Browser
checks use real Keycloak authorization-code redirects/password form/PKCE, not a simulated token
endpoint. Backend session fixtures are explicitly administrative test setup, not a login bypass.

F04 remains responsible for complete V2 object authorization, signed MCP context, persisted worker
identity and closure of the Full V1 compatibility surface. F05 still owns durable worker jobs.

References: [Keycloak containers](https://www.keycloak.org/server/containers),
[realm import](https://www.keycloak.org/server/importExport),
[fixed hostname](https://www.keycloak.org/server/hostname),
[PyJWT validation](https://pyjwt.readthedocs.io/en/stable/api.html).
