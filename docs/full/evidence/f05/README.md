# F05 evidence

26 October 2026; canonical Full worktree
`C:/Users/user/.codex/worktrees/opspilot-full-f01/AI Incident & Operations Agent`.
Branch codex/opspilot-full; base a332965b4d0fcbd2095aaaf9d5c8b3ff3dc77fdc.
Commit subject: feat(full): implement F05 durable jobs and independent worker.

## Measured gates

The current stage entry point is `powershell -NoProfile -File scripts/test-full-f05.ps1`.
The final implementation was built with:

```powershell
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml build api tests
powershell -NoProfile -File scripts/test-full-f05.ps1 -SkipBuild
```

Main backend: **205 passed, 6 skipped**; Ruff and format passed; mypy passed for **97 source files**.
The six skips are four destructive fixture migration checks, one legacy dedicated process entry point,
and the new dedicated process test, which was then run separately. Three inherited checkpoint recovery
cases (pause/committed decision/committed local write) passed inside the main 205; they are not extra cases.
Real OIDC/browser suite with the separate Compose worker: **12 passed**.

The first process run reached verified completion but its final attempts assertion exposed a test
race: a two-second delay expired before the duplicate-worker subprocess exited, allowing the claimed
start to finish before SIGKILL. The test-only execute delay was changed to 60 seconds so the parent
kills the process while the claimed run remains queued. No production code changed after the main
backend/browser gates. Ruff/format were rerun and the tests image was rebuilt. Final dedicated gate:

```powershell
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml up -d --wait postgres oidc mcp
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml run --rm --no-deps -e TEST_QUEUE_PROCESSES=1 tests python -m pytest -p no:cacheprovider -q tests/integration/test_durable_jobs.py
```

**5 passed**, including four repeated main cases and one new real-process case: **206 unique backend
cases** overall. These final gates cover:

- API process exit 73 after start commit before HTTP response; identical create replays the same run.
- Worker offline leaves the job/run queued; an independent worker claims it; a second worker is rejected.
- SIGKILL after committed claim before graph invoke leaves running job/queued run; new worker restores
  it with backoff, finishes pause, and the start job has exactly two attempts.
- API exit 73 after approval/job commit before response; identical decision replay while worker is
  offline; a separate worker resumes with persisted operator context, drains active resume on SIGTERM,
  verifies actual local ticket data and records exactly one ticket and one resume attempt.
- Enqueue failures roll back run creation and approval/status changes; no orphan resume job exists.
- Attempts/backoff and five-attempt dead-letter; safe error codes without injected private details.
- FORCE RLS/default-deny, foreign-tenant claim/read/insert denial and immutable queued budget limits.

Final scripted regression command (dirty implementation snapshot at the base commit):

```powershell
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml run --rm --no-deps evals python -m opspilot.evals.runner --mode scripted --commit a332965b4d0fcbd2095aaaf9d5c8b3ff3dc77fdc --dirty
docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml stop
```

**12/12**, hard safety gate true. These are inherited scripted regression cases, not F22's future
50-case suite. [JSON](evals/scripted.json), [summary](evals/scripted.md), [counts](checks.json).
Raw ignored logs: .tools/f05-final.log (main/browser), .tools/f05-process-final.log (corrected
process gate), .tools/f05-evals-final.log, .tools/f05-live-sdk.log. Test project stopped without
removing volumes. No remote CI run or paid model/vendor calls are claimed.

## Live Full and MVP preservation

Only dev Full api/mcp/worker/web were stopped for migration. Its admin service upgraded 0005 to
0006, then `docker compose -p opspilot-full -f compose.full.yaml up -d --wait postgres oidc collector
jaeger mcp api worker web` returned ready/running services. Full UI 8091 and API 8011/health returned
200; schema query returned 0006_command_jobs. Real scoped MCP SDK smoke negotiated 2025-11-25,
listed nine tools, returned GreenShop and NOT_FOUND for an unknown customer. Dev Full's single worker
remains running. Ports 8181/16696, Full database and volumes remain isolated.

Preservation command, executed before implementation and again after Full rollout:

```powershell
scripts/check-full-isolation.ps1 -MvpPath 'C:/Users/user/Desktop/code/AI Incident & Operations Agent' -ReportPath docs/full/evidence/f05/mvp-isolation.json
```

[Before](mvp-before.json), [after](mvp-isolation.json): all 184 tracked source/media/docs/.env hashes,
MVP main/HEAD f9f8d79, four image tags, volume metadata and read-only content SHA256 match the saved
F01 baseline. The original MVP git status is clean. No MVP service was started, restarted, migrated
or rebuilt. The baseline's volume-timing limitation is preserved explicitly in both reports.

## Scope and limits

[Queue semantics/runbook](../../durable-jobs.md). Graph/policy blobs unchanged, public state and
signed service context version 1; checkpoint SDK migration 9; schema 0006_command_jobs. Only one
worker is supported. Leases/epochs/checkpoint fencing and two-worker operation remain F06;
transactional events/audit/outbox remain F07. Conservative interrupted-investigation failure remains
explicit. F05 blockers: none. Next stage F06 is not started.
