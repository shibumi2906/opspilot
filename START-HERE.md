# OpsPilot Full — start here

**Portfolio edition complete · 20 November 2026.**
Start with the [README](README.md), [guided tour](docs/full/showcase-tour.md) and
[completion record](docs/full/portfolio-completion.md). Production/L2 hardening is
a separate future scope. The completed MVP is outside this work and stays unchanged.

## Review without infrastructure

The README includes actual Full screenshots, the preserved MVP video, architecture
and links to measured tests/scans/restore evidence. A local contract check needs
Python3.12 and uv, with no model key, Docker or private configuration:

```powershell
uv sync --frozen --python 3.12
uv run --frozen pytest -q tests/unit/test_full_backup.py
uv run --frozen python scripts/check-full-portfolio.py
```

The [GitHub Actions workflow](.github/workflows/f22.yml) is the clean ephemeral
Full verification route. Its initializer is deliberately restricted to GitHub-hosted
runners and is not a workstation setup script.

## Prepared interactive pilot

The existing local showcase is **opspilot-full-test-f23-recovery4**. Its private
configuration under .tools is intentionally absent from Git. A clean clone does
not contain the credentials, TLS CA, manager recovery state or database volumes.

| Component | Local address |
|---|---|
| Full workspace | https://app.opspilot.localhost:8443 |
| OIDC provider | https://idp.opspilot.localhost:8543 |
| Manager | Loopback-only18270; operator access only |

Use only the synthetic pilot identities stored privately in its credentials/OTP
fixtures. Keep these files and all session material out of screenshots, Git and chat.
The pilot uses a private local CA; the automated capture validates two exact leaf
SPKIs. Keep certificate verification scoped to the lab rather than disabling it globally.

To resume the **existing prepared instance**, from the Ops checkout with Docker
Desktop running:

```powershell
$pilot = '.tools/opspilot-full-test-f23-recovery4'
if (-not (Test-Path "$pilot/compose.json")) { throw 'Prepared pilot configuration is required' }
docker compose -p opspilot-full-test-f23-recovery4 -f "$pilot/compose.json" up -d --wait --no-build --no-deps postgres redis oidc
docker compose -p opspilot-full-test-f23-recovery4-manager -f "$pilot/manager/compose.json" up -d --no-build
.venv/Scripts/python.exe scripts/full_backup.py refresh-identities --config .tools/full-backup-operations/config.json
docker compose -p opspilot-full-test-f23-recovery4 -f "$pilot/compose.json" up -d --wait --no-build --no-deps collector mcp api worker web
```

These commands resume retained data and refresh short-lived service tokens. They
do not run seed/bootstrap, migrations, image builds or Jira enrollment. If the
private configuration or preserved volumes are missing, use the restore runbook
instead of initializing over an existing environment.

## Operations and preservation

- [Backup runbook](docs/full/f23-operational-backups.md): local copies at03:00/15:00,
  token refresh every30min. Both require the owner session and Docker Desktop.
- Before deliberately stopping this pilot, disable only its two owned Windows tasks
  and let any active capture finish. Preserve all volumes, keys and archives.
- Main Full development remains schema0019 in its own project. Do not implicitly
  promote the schema0023 showcase or remount old PostgreSQL data into a different image.
- Unknown Jira operations retain their original receipts. The showcase has no enabled
  Jira binding and does not retry those operations.
- Do not enable BitLocker: the owner's separate deferral remains in force.
- Do not change, reset, stage or rebuild the completed MVP. Existing dirty work there
  is not an issue to repair for this portfolio.

See [CURRENT-HANDOFF.md](CURRENT-HANDOFF.md) for the final scope and local CI pointer.
[Historical operator notes](START-HERE-HISTORY.md) retain earlier stage instructions;
they are not the current completion checklist.
