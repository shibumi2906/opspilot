# Local TLS pilot continuation — 16 November 2026

Owner-selected target: this Windows host, private local CA, HTTPS application8443
and IdP8543. The final project is `opspilot-full-test-f23-recovery4`, using internal
business network85, web/IdP edge86 and manager-only management network87.
No Jira enrollment or paid model calls. Main Full schema0019 and MVP are preserved.
The local CA was not installed into Windows trust; automated clients explicitly
validate that CA or the two generated leaf SPKIs.

| Measured check | Result | Evidence |
| --- | --- | --- |
| Native TLS / trust / plaintext rejection | 8 passed | [TLS probes](tls-probes.json) |
| Browser OIDC, separate approver MFA, session/SSE revoke | 14 passed; repeated after admin MFA | [Browser](browser-after-admin-mfa.json) |
| Actual IdP master administrator MFA | 7 checks; password-only and invalid OTP denied | [Admin MFA](admin-mfa.json) |
| Whole-pilot encrypted backup | 59 tables, 5 named-volume archives, private configuration | [Final backup](whole-pilot-backup-opspilot-full-test-f23-recovery3.json) |
| Cold restore with patched images | 63.88 seconds, 59 hashes matched before writes | [Final restore](whole-pilot-restore-opspilot-full-test-f23-recovery4.json) |
| Restored workflow / receipt / MFA | committed extra tickets0, pending new ticket1; restored admin MFA works | [Browser](final-restored-browser.json) |
| Final target manager rotation / revoke / seal / CAS rollback | 8 passed | [Manager](manager-rotation-opspilot-full-test-f23-recovery4.json) |
| Controlled deployment rollback | incompatible API readiness503; pinned API restored; all59 tables unchanged | [Rollback](deployment-rollback.json) |
| Fresh raw runtime image scans | HIGH/CRITICAL0 in all6 exact images | [Final gate](images-r2/gate.json) |
| Running container / scan identity | 9 containers match6 scanned runtime images | [Matching](runtime-scan-matching.json) |

[Final manifest](final-release-manifest.json) retains source image provenance and
the encrypted backup hash. Runtime Python/migration source matched183 files and
web assets matched the current build before deployment. The source was a dirty
snapshot of4059e45; its Jira implementation is now preserved in68c7d65.

The cold restore timer starts before key retrieval and decryption and includes
configuration, fresh volumes and empty database, manager unseal/token refresh,
IdP and service startup and browser approval smoke. Images are preloaded on this
documented host; this is not an OS rebuild or a general RTO/SLA promise. Application
roles were NOLOGIN and the restored database read-only until the59-table comparison
and pending checkpoint/committed receipt checks completed. Business services have
only the internal network, and no Jira destination is enrolled.

Backups contain a logical database dump, IdP state, manager encrypted data/audit,
paired collector journal/seal and private PKI/secret configuration. Plaintext dumps
were kept in memory. The envelope key is in a separate ignored directory. Both key
and archive are on this host; this is not an off-host recovery boundary.

Failed attempts remain visible. Pilot1 failed loopback publishing on an internal
network. The first admin probe misinterpreted Keycloak's hidden raw OTP secret as
Base32 and did not finish registration; private incomplete state was preserved.
Recovery1 failed on precreated schemas, recovery2 on a v1/v2 probe assumption:
[attempt1](restore-attempt1.json), [attempt2](restore-attempt2.json).
The earlier successful65.77s restore is [historical](whole-pilot-restore.json).
The initial image scan found3 web and19 PostgreSQL HIGH findings and blocked release:
[initial gate](images-r1/gate.json). Separate f23 images fix libxslt and krb5-libs;
the final restore uses those exact scanned digests. Preserved PostgreSQL volumes
were never mounted into the new runtime; recovery used a logical dump into a fresh volume.

This is scoped pilot evidence, not Full/ASVS L2 acceptance. Remaining operator and
release gates include host storage encryption (the Windows status query was denied),
an actual host OS vulnerability assessment, an operational ≤24h backup schedule
with7 daily/4 weekly retention and protected recovery arrangements, final SHA CI,
and requirement-specific review of all253 ASVS rows including reviewed N/A.
The generic IdP policy report's historical admin-MFA limitation is superseded only
for this local administrator by the separate actual MFA proof; production mail,
notifications and managed recovery have not been demonstrated.
