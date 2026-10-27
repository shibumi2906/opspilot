# F08 — clarification and cancellation evidence

Only F08 of OpsPilot_Full_Project_Specification.md is implemented. Full worktree:
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
branch `codex/opspilot-full`, base F07 `bd2350178597f6dff191d5d1e206a49841a503c8`.
Workflow full-graph-v1; state/DTO/event schema 1; checkpoint SDK migration 9;
database revision 0009_human_commands. [Contract/runbook](../../human-commands.md).

## Reproduction and final measurements

`powershell -NoProfile -File scripts/test-full-f08.ps1`

Compose project `opspilot-full-test-f08-release`, database `opspilot_full_test`, no test
ports published. Stop the dev Full stack while running the full gates on this host;
MVP and unrelated stacks must remain untouched. Normal timing is 30/10-second lease/
heartbeat; inherited subprocess fault gates explicitly use 3/1 seconds.

| Check | Final measured result |
| --- | --- |
| Ruff check / format | passed, 151 files |
| mypy | passed, 102 source files |
| TypeScript / Vite / Compose config | passed |
| Complete backend | 239 passed, 9 dedicated skips; 219.49 seconds |
| F08 cases included in backend | 18 passed |
| Browser / real OIDC, two workers | 12/12 |
| Queue subprocess suite | 5/5; 43.54 seconds |
| SIGKILL / SIGSTOP / TCP partition | 3/3; 37.66 seconds |
| Scripted regression | 12/12, hard safety gate true |

**243 unique backend cases** = 239 main + one additional queue case + three fencing
cases. Four queue cases repeat the main suite; no repeat is counted twice. Earlier
focused preflight had 23 passes (18 F08 + five execution faults), also not additional.
[Counts/source fingerprints](checks.json), [eval report](evals/scripted.md),
[SIGKILL](process/kill.json), [SIGSTOP](process/stop.json), [partition](process/partition.json).

The 18 F08 cases cover ambiguous Green in RU/EN, a new OS process reopening a pending
interrupt, restart after answer commit, exact command replay across rounds, forged/stale/
opposite answers, answer/cancel transaction rollback, integration selection, two-round cap,
expiry, an accepted answer surviving queue delay, same-tenant foreign-owner/role/tenant HTTP
denies, queued/running/both waiting cancellations, both sides of a committed-response race,
and cancellation blocked by an open local write transaction. Another regression pauses
after execute-node entry, commits cancellation and proves zero subsequent write tool calls
and execution_status=not_started. Known cancellation is handled inside the MCP transport
context so its task group cannot turn it into an unknown write.

DST checks use October 24 and 26. Midnight on the October 25 transition day is before
the clock change and still has the earlier offset. Eval E06 now explicitly expects a
pending input form with no final report, target selection or write; it is not presented
as a completed insufficient-context investigation. It retains the zero-write safety gate.

## Live Full and preservation

Dev Full was upgraded 0008→0009, then restored with final sources and two healthy workers.
The synthetic live probe observed queued → waiting_for_input → queued → waiting_for_approval
→ cancelling → cancelled, with the same form after reopening, one idempotent answer command,
a cancelled unexecuted action, matching event/audit counts and an empty outbox. MCP protocol
2025-11-25 exposes nine scoped tools; UI 8091/API 8011 return HTTP 200. [Live evidence](live.json).

Reproduce the probe against the isolated dev Full stack:
`docker compose --env-file .env -p opspilot-full -f compose.full.yaml run --rm --no-deps -v "${PWD}/scripts/smoke-full-f08.py:/probe.py:ro" api python /probe.py`.
The probe asserts scripted mode and actual Full database/schema before application calls.

MVP 184 source/media/docs/.env fingerprints, main/HEAD, four image tags, volume metadata
and read-only volume-content hash match [before](mvp-before.json) and
[after](mvp-isolation.json). The initial F01 volume-baseline timing limitation remains
explicit in those reports. The original checkout is clean; no MVP service was started,
migrated or rebuilt. F01–F07 evidence remains unchanged. Provider/vendor calls and paid
LLM cost are zero; application destinations are local synthetic OIDC/PostgreSQL/MCP.
Remote CI, F09 approvals/revisions, F14 UI, F21 load and F22 real/holdout gates are not claimed.

## Failed candidates and diagnostics

Failures are not counted as passes. Earlier candidates exposed an old readiness schema pin,
a missing next-round run projection, an incorrect test helper/DST expectation and a mypy
annotation. The added dispatch regression exposed transport ExceptionGroup handling; this
was fixed and the final full backend passed. A later recovery fixture marker timed out;
it now retains stderr and fails promptly on terminal errors, without changing its 30-second
limit. Cancellation checks reuse the worker-owned engine, and dev Full was stopped during
final tests. An accelerated drain worker once exited 1 and an accelerated kill successor
once reached conservative RESTART_INTERRUPTED before a first safe checkpoint, with no write.
Original transient causes are unconfirmed; the complete queue suite, independent drain repeat
and complete three-fault suite subsequently passed with unchanged timings and assertions.

Final backend/browser/queue log: `.tools/f08-release-final.log`; final fault/eval commands:
`.tools/f08-faults-final.ps1/log`; final live rollout: `.tools/f08-deploy-final.log`.
The release script runs all gates in sequence. Eval output uses the unique `/reports-f08`
mount plus explicit `--output` to avoid the inherited F07 report mount. The routing was
verified by a local marker probe. Fresh final eval files were moved here and previous F07
files restored byte-for-byte from HEAD; no F07 evidence changes remain.

Commit subject: `feat(full): implement F08 durable clarification and cancellation`.
