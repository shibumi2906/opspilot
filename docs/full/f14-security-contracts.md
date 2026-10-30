# F14 — workspace security contracts

Base F13 2fe6613. Scope: browser history/search/filters, existing human commands, inbox/read,
minimal tenant admin connectors/memberships/account sessions, audit and bounded redacted export.
No new write tools, provider destinations, arbitrary URLs/SQL, credential input, or grant fields.

Private request/evidence/body data stays in authorized run DTOs or the addressed recipient inbox.
Export is a separate allowlist: IDs/status/timestamps and redacted audit metadata; no request,
evidence excerpts, action bodies, secret refs, private state, raw audit diff, token or credential.
Actor/tenant/filter/stream-bound MAC cursors and size limits apply before every query.
Admin alone cannot read domain runs/audit; auditor can read tenant audit, operator owns its runs.
Global account disable/revoke requires existing exclusive managed scope. Membership editing may
manage an existing member or provision an unassigned identity, never import a foreign-only identity.
Admin mutations require fresh authentication, exact origin/CSRF and uncached role locks.

Inbox read markers are separate from immutable receipts, tenant/recipient RLS and idempotent.
Connector controls permit enabled only with expected_version; no URL/credential/tenant mutation.
Admin setter locks integration before control row, same order as effect preconditions. Disabled
connections fail closed in Core/MCP; changed control versions invalidate old consent. Version0
omits the extra precondition field, preserving unmodified F13 revisions during upgrade.

Browser role gates only guide UX; server authorizes every read and mutation. Plain React text,
fixed safe routes, no HTML rendering, CSP/HSTS/no-store/cookies preserved. Private views clear on
401/403/tenant change/revoke; offline never extends server session deadlines. Commands serialize
and reconcile from saved state, without automatic resubmission of writes.

SEC-01/02/06/08/10 gates: real DB negative scope/CAS/idempotency/export tests, multi-role/two-tenant
Chromium, XSS/offline/revoke/focus/mobile checks, fresh native TLS/MFA and distinct IdP policy report.
Recovery uses the pinned IdP account console; this BFF never handles passwords/TOTP recovery.
Production mail, IdP administrator MFA and managed secrets remain explicit F17/F23 obligations;
local disabled self-service reset is fail-closed, not proof of a production recovery service.
Full ASVS L2 remains NOT_MET; primary requirement dispositions need individual evidence/review.

## Provider and password policy

Full pins Keycloak 26.8.1 by OCI index digest; the baseline was 26.2.5. The selected release
was verified against the [official downloads](https://www.keycloak.org/downloads) and
[upgrade guide](https://www.keycloak.org/docs/latest/upgrading/index.html). Before touching the
persistent local realm, quiesce IdP and save its volume under ignored `.tools` (contains private
identity data). Fresh TLS tests and a preserved-data upgrade check precede acceptance.
No rollback to an older provider against an upgraded H2 database is supported; restore the
quiesced backup to a separately isolated recovery volume when needed.

The realm accepts long passwords without composition rules, requires at least15 and at most128
characters, rejects username/email and a pinned compromised-password list, remembers5 prior
passwords, and requires immediate reauthentication for account-console credential changes.
The local synthetic password fixtures remain outside committed artifacts. Runtime blocklist is
read-only, lowercase/deduplicated with source/hash/license in `password-blacklists/source.json`.
See [Keycloak password policies](https://www.keycloak.org/docs/latest/server_admin/index.html#password-policies).
Brute-force delay and security/admin event recording are enabled; sensitive admin event details
are disabled. The separate TLS policy probe creates a temporary synthetic identity, verifies
length/denylist/history rejection, and deletes it in a finally block. It never sends email.

The account link is assembled only from the pinned configured issuer. Password reset is disabled
until a verified mail/recovery deployment exists; operators contact their authorized identity
administrator. The account console manages existing factors; production factor-change notification,
mail delivery, independent identity verification during recovery and administrator-plane MFA
remain open and must be demonstrated at F23. Local synthetic policy evidence does not close those
norms or establish whole-application ASVS compliance.

## Image remediation provenance

The unmodified26.8.1 candidate scan is retained with3 HIGH findings (Java runtime and Guava).
The accepted runtime must use the supported Java21 LTS from a digest-pinned Debian base with
its exact security-fixed JRE package and checksum-pinned Guava33.7.2-jre. The package database
is retained for OS/JRE scanning. The original Guava bootstrap filename is preserved; embedded
Maven metadata and bytes identify the fixed artifact. No package metadata is removed and no
scanner ignore is introduced. A RHEL Java25 candidate retaining15 HIGH findings was rejected.
See `infra/identity/security-patches.json` for primary vendor advisories and artifact provenance. Native OIDC/TLS policy checks must be repeated for
the resulting custom image; the unmodified image's passing UX results do not close this gate.


### Exact component applicability

The raw final IdP Trivy report is retained with **4 HIGH** findings attributed to the
util-linux source package through libuuid1. This is not a raw-zero scan. The upstream
advisories identify libmount mount hooks/detached-tree code or nsenter cgroup migration
code; neither component is shipped in the final image. `scripts/check-f14-idp-applicability.py`
checks the scan image ID against the archive config digest, verifies every layer diff ID,
reconstructs the final filesystem including whiteouts, requires the exact reviewed libuuid
SHA256 and only UUID exported symbols, and rejects any affected libmount/mount/nsenter entry.
BusyBox's separate static mount applet is disclosed and retained. Package metadata stays intact.

`docs/full/evidence/f14/security/vulnerability-applicability.json` binds the assessment to the exact final image,
raw report hash and four CVE/advisory IDs. Applicable HIGH/CRITICAL is zero only after this
proof; any other finding, package/version, library bytes or image mismatch fails the gate.
Negative checks demonstrate rejection of unexpected CVE/package/image identity. This is a
component applicability assessment, not risk acceptance, a scanner ignore or ASVS requirement
N/A. Primary sources: [mount post-hooks](https://github.com/util-linux/util-linux/security/advisories/GHSA-m25x-3hj9-m26f),
[nsenter](https://github.com/util-linux/util-linux/security/advisories/GHSA-55fx-f4gg-cfhj),
[detached tree](https://github.com/util-linux/util-linux/security/advisories/GHSA-8f2p-47x3-43mv),
[bind source](https://github.com/util-linux/util-linux/security/advisories/GHSA-rh77-686x-2f2m).
