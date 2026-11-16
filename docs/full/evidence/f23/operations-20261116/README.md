# F23 local operational checks — 16 November 2026

Scope: scripted `opspilot-full-test-f23-recovery4`; no Jira enrollment, provider
POSTs or paid LLM execution. Main Full schema0019 and MVP remain preserved.

| Evidence | Observed result |
|---|---|
| [host-assessment.json](host-assessment.json) | Elevated read-only OS/Defender/TPM and fresh online Windows Update assessment; C: unencrypted |
| [recovery-preparation.json](recovery-preparation.json) | One recovery protector/local file prepared; encryption not enabled; owner later explicitly deferred it |
| [schedule-installed.json](schedule-installed.json) | Two actual Windows tasks, background pythonw, limited interactive owner, no stored Windows password |
| [scheduler-verification.json](scheduler-verification.json) | Backup and token-refresh LastTaskResult0 |
| [backup.json](backup.json) | Scheduled encrypted copy,59 tables/five volumes, former services resumed, authenticated retention applied |
| [offline-restore.json](offline-restore.json) | Latest scheduled copy restored into fresh networkless/NOLOGIN/read-only DB;59 hashes matched, five volume archives parsed |
| [refresh-identities.json](refresh-identities.json) | Scheduled worker/MCP identity refresh preserved existing keys/ACL |
| [status.json](status.json) | Retained encrypted copy authenticated and younger than24h at observation |
| [unit.xml](unit.xml) | 35 tests passed: backup7, OIDC and HTTP security; initial34-test report also preserved |
| [followup-unit.xml](followup-unit.xml) | Follow-up37 tests passed: backup9 plus unchanged OIDC/HTTP cases |
| [private-acl.json](private-acl.json) | Four actual private directories: protected inheritance, no allow rules outside owner/SYSTEM/Administrators |
| [offline-restore-guarded.json](offline-restore-guarded.json) | Fresh third offline restore after adding Docker-name collision guards;59 tables matched |
| [native-lock-serialization.json](native-lock-serialization.json) | Real scheduled refresh waits for an occupied lock and completes0 after release |
| [mvp-before-restore.json](mvp-before-restore.json) | Read-only isolation before fresh restore |
| [mvp-final.json](mvp-final.json) | Final source/env/branch/images/volumes isolation gate passed |
| [secret-check.json](secret-check.json) | Public candidate files and ten pilot log streams contain no exact known secrets or JWT shapes |
| [ci-688c5cc.json](ci-688c5cc.json) | Previously authorized push and successful remote CI at688c5cc; not CI for this new change |
| [ci-f34b94d.json](ci-f34b94d.json) | Operational base CI: Full50/MVP12, Jira45, units12+backup7, security/secret gates and144 source hashes verified; follow-up guards require their own final SHA |

First console scheduled launch returned `3221225786 / 0xC000013A`; no new archive
was committed. Some services had stopped. The original service set was restored
explicitly. This led to background pythonw/CREATE_NO_WINDOW and a durable pre-stop
resume journal. Later scheduled launches succeeded. Unit cases cover interrupted
resume and preservation on failed resume; no deliberate second host power-off was run.

[One subsequent overlap](scheduler-lock-contention.json) returned1 when a manual
refresh collided with offline restore. The lock was then changed to bounded waiting
and its Windows locked-byte initialization corrected. The seven backup tests and
native12-second lock/scheduler verification passed afterward. No historical failed
run is reclassified as successful.

The first follow-up ACL implementation could not load the nested Windows PowerShell
Security module. Its failed JUnit remains ignored at
`.tools/host-review-20261116/followup-unit-acl-failed.xml`; no key is included in public
reports. The helper now calls the framework directory access-control API directly,
then the37-test run and native exact-principal ACL audit passed.

Retention actually removed superseded same-day copies only within the new owned
backup store. An earlier copy was verified in fresh offline target
`opspilot-full-test-f23-scheduledrestore1`; the retained scheduled copy was verified
in `opspilot-full-test-f23-scheduledrestore2`. Both recovery databases were stopped;
their volumes/private configs remain preserved. The main/preserved Jira labs were
never selected. Historical backup archives were not subjected to this retention.

Daily and weekly histories accumulate over time; this does not claim four weeks
of elapsed operation. Machine-off time and loss of C:/the PC are outside this local
schedule's protection. The two retained key/archive locations are separate directories
on the same physical host. A full runtime restore63.88s was measured separately in
[the earlier pilot rehearsal](../local-pilot-20261116/README.md); the new offline
verification does not replace that test or measure a fresh whole-system RTO.

[Operator runbook](../../../f23-operational-backups.md).
[253-row assessment and remaining release gaps](../../../../security/release-review-20261116/README.md).
Full Pilot/ASVS L2 remain **NOT_MET**.
