# F14 — scoped operations workspace

Base: F13 `2fe6613`, branch `codex/opspilot-full`; separate Full worktree. MVP source,
.env, image tags and volume contents are checked before and after this stage.

Implemented: authorized history with MAC-bound cursor/filter state; typed clarification and
Cancel; exact-revision editing/revocation/TTL display; mixed action decisions and explicit
unknown/partial reconciliation presentation; recipient inbox with separate idempotent read
markers; minimal admin memberships/account-session controls and connector enable/version CAS;
auditor-only redacted audit, bounded allowlisted downloads; pinned IdP account/recovery link.
No arbitrary connector URL, credential or grant fields are exposed in product forms.

Migration `0015_workspace` adds FORCE-RLS marker/command/control tables and bounded fixed-path
SECURITY DEFINER functions with narrowly granted execution. Connector disabling fails closed
through the existing Core/MCP precondition function; changing or re-enabling increments its
version and requires new consent. Default version0 preserves untouched F13 preconditions.
Membership edits serialize per tenant, reject stale expected roles, foreign-only identity
imports and removal of the final enabled administrator. Admin is not a run-reading role.

React text rendering is used for private notification and audit content. Tenant switching
clears the private workspace immediately; server authorization remains authoritative. Selecting
the currently open run from History refreshes its saved snapshot without dropping the reader.
Expiry has a local deadline timer; actual consent TTL remains enforced by DB time in Core/MCP.

Provider: Keycloak 26.2.5 -> digest-pinned26.8.1, with an exact security-fixed Java21 LTS package on a pinned Debian base and checksum-pinned Guava33.7.2-jre remediation. Startup is gated by native readiness rather
than container creation. Password blocklist source/license/hash are pinned; local minimum15,
maximum128, history5, brute-force delay and security events are tested separately from BFF UX.
Self-service reset remains disabled until verified recovery delivery exists. Production mail,
factor-change notifications, identity recovery procedures and administrator MFA remain explicit
F23 deployment obligations; full ASVS L2 is NOT_MET.

## Verification

Final results and image binding are recorded in `checks.json`; complete logs and raw scanner
reports accompany it. The backend final gate passed387 tests with9 dedicated process skips.
The source-match report binds120 application files plus migrations to the runtime package.
All later frontend/provider fixes are verified by the final browser, native TLS/MFA and live
Full checks rather than being represented as a new backend run.

Browser matrix includes real OIDC roles/two tenants, mixed decisions, revision consent,
clarification/Cancel/history/download, private inbox and XSS text, role-separated admin/audit,
mobile overflow and keyboard/focus. Expiry/unknown UI boundary uses labelled response fixtures;
real DB-time expiry, unknown receipts and no unauthorized writes are covered by integration
and process tests. Synthetic destinations are used; no external vendor writes or paid calls.

## Candidates and reproducibility

Candidate failures are retained as diagnostic evidence: initial membership lock required a
privilege it did not have (removed that lock, retained tenant advisory serialization); quoted
SQL return-column syntax; expanded public-config allowlist assertion; same-run History reset;
wrong notification button selector; and waiting for tenant navigation. Provider upgrade exposed
a missing readiness gate. These candidates are not accepted as passing release results.
Large Java scan-index acquisition is cached separately in a Full Docker volume and verified
against its official OCI layer digest; a failed or partial download is never accepted as a scan.

Reproduce with `scripts/test-full-f14.ps1` and `scripts/test-full-f14-tls.ps1`.
The former runs build/migration/static/backend/browser/process/eval/supply-chain gates; the
latter creates a fresh ignored native TLS/MFA realm and writes distinct IdP policy evidence.
Local rollout uses `scripts/deploy-full-f14-local.ps1`, preserving quiesced domain/action hashes
and an ignored private IdP backup before upgrading. No push or future stage is part of F14.

The unmodified26.8.1 image is retained as `security/oidc-unpatched-candidate.json` with3 HIGH
findings. `infra/identity/security-patches.json` documents vendor advisories and exact artifacts.
Final acceptance requires a new full image scan, the actual JRE/Guava/truststore probe and
repeated OIDC/native TLS checks on the custom image. Upstream package vulnerability metadata is retained;
no scanner ignore or metadata removal is used to claim remediation.

Final runtime preparation keeps the vendor Keycloak distribution and launcher but uses the
pinned minimal Java21 distroless filesystem, including its upstream static BusyBox shell.
The normal Debian builder supplies the security-fixed toolchain; it is not shipped as runtime.
The original package metadata from the final base is retained. The compiled Java probe checks
readiness, actual JRE version, the exact fixed Guava hash and a nonempty default truststore
without the compromised root. Full Debian/RHEL candidate scans are retained rather than hidden.
The legacy single-action `unknown_outcome` branch also exposes read-only reconciliation even
when its outer run status is completed; this does not authorize a write retry.


### Exact component applicability

The raw final IdP Trivy report is retained with **4 HIGH** findings attributed to the
util-linux source package through libuuid1. This is not a raw-zero scan. The upstream
advisories identify libmount mount hooks/detached-tree code or nsenter cgroup migration
code; neither component is shipped in the final image. `scripts/check-f14-idp-applicability.py`
checks the scan image ID against the archive config digest, verifies every layer diff ID,
reconstructs the final filesystem including whiteouts, requires the exact reviewed libuuid
SHA256 and only UUID exported symbols, and rejects any affected libmount/mount/nsenter entry.
BusyBox's separate static mount applet is disclosed and retained. Package metadata stays intact.

`security/vulnerability-applicability.json` binds the assessment to the exact final image,
raw report hash and four CVE/advisory IDs. Applicable HIGH/CRITICAL is zero only after this
proof; any other finding, package/version, library bytes or image mismatch fails the gate.
Negative checks demonstrate rejection of unexpected CVE/package/image identity. This is a
component applicability assessment, not risk acceptance, a scanner ignore or ASVS requirement
N/A. Primary sources: [mount post-hooks](https://github.com/util-linux/util-linux/security/advisories/GHSA-m25x-3hj9-m26f),
[nsenter](https://github.com/util-linux/util-linux/security/advisories/GHSA-55fx-f4gg-cfhj),
[detached tree](https://github.com/util-linux/util-linux/security/advisories/GHSA-8f2p-47x3-43mv),
[bind source](https://github.com/util-linux/util-linux/security/advisories/GHSA-rh77-686x-2f2m).


## Preserved-data rollout and interruption recovery

The rollout was interrupted after schema0015 committed but before final readiness. On30 October,
the schema was inspected before any retry. Exact domain/action counts and hashes matched the
committed F13 preserved-data snapshot; `rollout-preservation.json` explicitly identifies that
baseline source. Migration was not replayed. The quiesced private IdP backup stayed ignored;
`idp-backup.json` records only its digest/readability, not its contents. The deployment helper now
persists its pre-migration fingerprint immediately so a later interruption retains that evidence.
Reviewed realm policy keys were applied without user/client/credential mutations. Live OIDC
workspace checks passed and both workers/UI/API were restored. The final MVP fingerprint passes.

Docker startup again encountered its stale OTel IPC socket after the overnight interruption.
The already-authorized recovery preserved only the IPC directory and restarted Desktop; data,
settings and volumes were untouched. All F14 test/lab containers and networks were removed;
volumes and images remain. Final accepted native TLS/MFA evidence uses the exact final IdP image:
8 TLS probes,14 browser checks,4 separate password-policy checks; SSE disable revocation605ms.
