# F02 evidence

2026-10-26, `codex/opspilot-full`, base `0d529b0eb3f31619e014e6d1e163a49b5f11e66c`,
dirty implementation snapshot. Commit subject: `feat(full): add F02 tenant isolation and safe fixture upgrades`.
Worktree: `C:/Users/user/.codex/worktrees/opspilot-full-f01/AI Incident & Operations Agent`.

| Gate | Measured result |
| --- | --- |
| Fresh schema / fixture upgrade / unknown-owner rollbacks | 4 passed |
| Backend on final tenant schema | 164 passed, 7 skipped |
| Dedicated process restart tests | 3 passed (the 3 recovery skips above) |
| Final checkpoint guards + actual saver/RLS/FK checks | 11 passed: 4 added DB guards and 7 repeated checks |
| Browser GreenShop approve/reject and existing UI regressions | 9 passed |
| Scripted inherited regression evals, real MCP/PostgreSQL | 12/12; hard safety gate true |
| Lint/format/types on final source | pass; 121 Python files formatted; mypy 84 source files |
| Live Full upgrade + seed + HTTP/SDK smoke | schema 0003, API/UI HTTP 200, actual MCP 2025-11-25 |
| MVP source/env/images/volumes | unchanged |

The 7 backend skips are 4 migration-only tests plus 3 process-recovery tests, all run separately.
There are 168 distinct passed backend cases (164 + 4 new guards), not 175 distinct cases from
adding the repeated 7 SDK checks. Four isolated migration gates are additional and kept separate.
The last direct-checkpointer DSN/current_database guard was added after the main image was built;
the final image passed the 11-case guard/real SDK rerun, final lint/types and live Full SDK smoke.
An attempted supplemental run overlapped the main script's test-DB shutdown; its transport failures
were rerun after explicitly starting PostgreSQL. No remaining failure is hidden by that retry.

## Reproduce

`powershell -NoProfile -File scripts/test-full-f02.ps1` builds the locked images, runs migration gates
in project opspilot-full-f02-migrations/database opspilot_full_test, then regression checks in
opspilot-full-test/database opspilot_full_test (different project volumes). It stops only these test
projects and preserves volumes. Destructive fixture reset code refuses non-test DSNs and validates
current_database; no MVP database is read for upgrade fixtures.

Final supplemental command (after `docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml up -d --wait postgres`):

```powershell
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml run --rm --no-deps tests python -m pytest -p no:cacheprovider -q tests/unit/test_full_database_guard.py tests/integration/test_checkpoint_compatibility.py tests/integration/test_tenancy.py::test_checkpoint_thread_is_hidden_from_other_tenant tests/integration/test_tenancy.py::test_checkpoint_cannot_reference_foreign_run_even_as_admin
```

Final lint/format commands use the same prefix and `tests ruff check --no-cache src tests migrations`,
`tests ruff format --check --no-cache src tests migrations`; types use `tests mypy --cache-dir /tmp/opspilot-mypy src`.

Live Full was stopped (only web/api/mcp), migrated via `docker compose -p opspilot-full -f compose.full.yaml run --rm admin`,
seeded via the same prefix and `admin python -m opspilot.cli.seed`, then started with
`up -d --wait postgres collector jaeger mcp api web`. The administrative seed reported two tenants,
6 customers, 20 incidents and 10 articles. Runtime-role flags, composite FK count and per-tenant rows
are in [schema-smoke.json](schema-smoke.json). CLI SDK smoke used the same Full prefix and
`run --rm --no-deps api python -m opspilot.cli.mcp_smoke`: protocol 2025-11-25, nine tools,
GreenShop read and NOT_FOUND for an unknown customer. GET 8011/health and 8091 returned 200.

Preservation command:
`powershell -NoProfile -File scripts/check-full-isolation.ps1 -MvpPath 'C:\Users\user\Desktop\code\AI Incident & Operations Agent' -ReportPath docs/full/evidence/f02/mvp-isolation.json`.
It matches all 184 original tracked/env fingerprints, main/HEAD, four MVP image tags and volume metadata;
the 1343-file read-only volume manifest also matches the saved F01 baseline (which predates F02).
MVP remains stopped/unchanged; its UI/config/ports were not repurposed or restarted.

## Artifacts and limits

- [checks.json](checks.json), [measured transcript](checks.txt).
- [Scripted case details](evals/scripted.json), [scripted report](evals/scripted.md).
- [MVP preservation](mvp-isolation.json), [Full schema smoke](schema-smoke.json).
- Raw local logs: .tools/f02-final-checks.log, f02-guard-sdk-checks.log, f02-live-sdk-smoke.log.

The report's inherited fixture hash identifies base.json; checks.json separately records the F02
seeder/migration hashes. Dependency locks and graph/policy versions are unchanged. The 12 inherited
MVP evals are Full-isolated regression evidence, not the future 50 Full eval cases.
No paid provider/Prometheus/Jira calls or remote CI run. Alembic emits seven non-failing path_separator
deprecation warnings in migration tests. OIDC, server-session issuance, full API/MCP authorization,
worker leases and checkpointer epoch fencing remain later stages. Public pilot remains closed.
