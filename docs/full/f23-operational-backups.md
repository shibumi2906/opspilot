# F23 operational backups — local recovery4

The selected scripted TLS pilot now has two Windows tasks:
`OpsPilot-Full-Backup-Recovery4` at03:00/15:00 local Windows time and at logon, and
`OpsPilot-Full-Secrets-Recovery4` every30 minutes and at logon. They run as the
interactive owner at limited privilege, use background `pythonw.exe`, and store no
Windows password. The machine, logged-in owner and Docker Desktop must be available.
StartWhenAvailable and two10-minute retries handle missed/failed launches. This is
a local pilot schedule, not an unattended server or off-host disaster-recovery SLA.

The actual scheduler returned0 for both tasks. A separate manual first capture
and subsequent scheduled captures succeeded. Latest captured copy restored into
a fresh offline PostgreSQL database:59 table hashes matched, all application roles
NOLOGIN, five volume payloads readable, no source migration or provider dispatch.
See [operational evidence](evidence/f23/operations-20261116/README.md).

## Capture and retention

`scripts/full_backup.py` validates the exact project, scripted mode, private network
and absence of enabled Jira bindings before quiescing. It captures logical PostgreSQL,
IdP, manager data/audit, collector journal/seal and private deployment configuration.
Application/IdP/manager writers stop during capture; PostgreSQL stays running for the
logical dump. Before/after hashes detect database changes. Only formerly running
services resume; stopped workers and operator tools are not implicitly started.
Service interruption is therefore expected during each scheduled local backup.

Plaintext stays in process memory. Fernet authenticates/encrypts the bundle; a separate
random key is stored per copy. Archive, key, configuration, errors and verification
directories have ACLs restricted to the owner, SYSTEM and local Administrators.
These local files remain ignored. Both copies and keys are currently on C:, so
this does not protect against loss of the PC/disk. Off-host backup remains an
operational deployment decision; C: encryption is still deferred by the owner.

Retention keeps the latest copy for each of seven available UTC dates and four
available ISO weeks, plus every held/incomplete copy. These are overlapping sets.
The history accumulates over time; seven days/four weeks of actual elapsed operation
have not been observed. Retention tests cover42 days with two copies/day.
Same-day superseded copies in this new owned store were actually pruned after
verification. Historical F20/F23 rehearsal archives and Jira r1 state are outside
this store and never pruned.

Every catalog entry must match its authenticated encrypted metadata and checksum
before any deletion. Unknown Jira outcomes hold a copy. Failed validation preserves
all files. Prune targets individual owned files only, never directory trees.

An OS handle lock serializes capture, refresh, verification and retention. A durable
pre-stop journal records the exact running services. A later backup/refresh resumes
an interrupted operation before proceeding; failed resume preserves the journal.
Seven unit cases cover retention, forged dates, lock contention and interrupted/unsafe resume behavior.
Automatic crash recovery has unit evidence; it has not been validated with a second
deliberate host power-off.

The lock waits up to10 minutes, within the20-minute task limit, so a token refresh
can wait for backup/offline verification. A native scheduler test held the lock12s,
observed the refresh task still running and verified successful completion after release.
Before this bounded-wait fix, one overlapping refresh/restore returned1;
that observed contention report remains preserved.

The first scheduled console launch returned `0xC000013A` and stopped some services
before capture. The old backup remained intact. The original service set was
explicitly restored, then tasks were changed to background pythonw and Docker
subprocesses to CREATE_NO_WINDOW. This failure is retained in the evidence rather
than presented as a successful scheduled backup.

## Operator commands

From the Ops checkout, while Docker Desktop is running:

```powershell
.venv/Scripts/python.exe scripts/full_backup.py status --config .tools/full-backup-operations/config.json
.venv/Scripts/python.exe scripts/full_backup.py backup --config .tools/full-backup-operations/config.json
.venv/Scripts/python.exe scripts/full_backup.py retention --config .tools/full-backup-operations/config.json
Get-ScheduledTaskInfo -TaskName OpsPilot-Full-Backup-Recovery4
Get-ScheduledTaskInfo -TaskName OpsPilot-Full-Secrets-Recovery4
```

Status authenticates retained copies and returns nonzero when the latest is older
than24h. Inspect both scheduler LastTaskResult and ignored per-mode results under
`.tools/full-backup-operations/opspilot-full-test-f23-recovery4`. Error traces stay
under `.tools/full-backup-errors`; never upload them without secret review.

Use `restore-verify --id <catalog-id> --target opspilot-full-test-f23-<fresh-name>`
with the same config to create a new networkless verification database. It refuses
existing recovery state, compares every table and stops the new database afterward.
It authenticates all volume payloads but does not start the recovered IdP/manager.
The separate full-pilot cold restore63.88s remains the runtime recovery evidence.

Before intentionally stopping the pilot, disable both exact owned tasks in an
administrator PowerShell and allow an active operation to finish. Re-enable after
the pilot is deliberately started. Never use these tasks on the preserved live-Jira
r1 project or point them at main Full. Manager token refresh preserves keys and ACL;
it does not reset factors or reconcile/retry provider operations.

## Host evidence and recovery key

Elevated read-only audit confirmed Windows11 Pro25H2 build26200.9974, Defender
antivirus/realtime enabled, TPM present/ready/enabled and fresh online Windows Update
assessment result2 with no pending software updates. This is a patch/configuration
assessment, not proof of an entirely vulnerability-free OS or third-party software.

C: is FullyDecrypted/ProtectionOff, including Docker VHDs. At the owner's request,
one recovery password protector and a private temporary file were prepared without
enabling encryption. The owner then explicitly said the off-PC copy is not yet saved
and asked not to enable BitLocker. Preserve that instruction. Do not read the key into
tool output, reports, Git or chat. Local file:
`.tools/host-recovery/BitLocker-C-recovery.txt`. Only after owner confirmation of an
independent recovery copy may the encryption step continue; do not force a reboot.

Microsoft documents [backing up the recovery key](https://support.microsoft.com/en-us/windows/security/encryption/back-up-your-bitlocker-recovery-key)
and [adding a recovery protector before enabling BitLocker](https://learn.microsoft.com/en-us/powershell/module/bitlocker/enable-bitlocker).
