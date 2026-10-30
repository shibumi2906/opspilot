# F15 evidence

Base F14 `be246d7`; isolated Full worktree, branch `codex/opspilot-full`.
[Measured checks](checks.json), [security contracts](../../f15-security-contracts.md).
Only F15 is accepted here. Future stages and full ASVS L2 remain open / NOT_MET.

## Accepted gates

- Backend402 passed,11 dedicated skips: [backend log](backend-final.log).
- Dedicated provider crash1 and actual Redis stop/recreate1 passed. PostgreSQL attempts/held
  tokens were unchanged; [restart counters](redis-restart.json). Focused19 checks are a subset.
- Real OIDC/Chromium22, queue processes5, fencing faults3 and scripted eval12/12:
  [release log](browser-process-security-evals-final.log), [process reports](process/kill.json),
  [scripted report](evals/scripted.json). Unauthorized/duplicate/false verified writes0.
- Native TLS8, Redis TLS/auth/cache6, MFA/browser14, distinct IdP policy4:
  [TLS log](tls-final.log), [Redis proof](tls/redis-tls.json), [browser proof](tls/browser.json).
  IdP disable closed an existing TLS SSE stream in344ms without polling /auth/me.
- Ruff/format/mypy123, TypeScript/Vite and PowerShell parsers pass. Runtime source binding:
  [123 Python files](source-match.json), [36 UI/browser files](ui-source-match.json),
  [3 served assets](web-artifacts.json), [changed source inventory](source-inventory.json).
- Raw OS runtime app/web/Redis HIGH+CRITICAL0; Python/npm dependency findings0. Unchanged
  IdP retains raw4 HIGH. [Exact-image/layer/ELF applicability proof](security/vulnerability-applicability.json)
  verifies affected libmount/nsenter code absent; applicable0. Raw scan retained, no ignore,
  metadata removal or risk acceptance. [Accepted/live images](images.json).
- Local0015→0016 Full migration preserved counts/SHA256 of12 pre-existing tables before workers:
  [preservation](rollout-preservation.json), [live OIDC/usage/refresh](live-usage.json),
  [restored Full](restored-full.json). UI8091/API8011 HTTP200, two workers and private Redis.
- MVP184 source/env fingerprints, branch/HEAD, images, volume metadata/content preserved:
  [initial prerequisite](mvp-before.json), [final isolation](mvp-isolation.json).
  F15 test/lab containers/networks removed; volumes/images retained.

## Scope and honest accounting

All provider tests use scripted fixtures or explicitly labelled HTTPX mock transports.
No paid calls, vendor writes, production deployment, remote CI or push. Unknown-cost UI uses
an identified response-boundary fixture; unknown usage, retries and crash reservations are
real PostgreSQL tests. Redis source caching does not count as provider prompt-cache savings.
[Versioned pricing sources](pricing-source.json) retain day-level review precision, explicit
project effective date/expiry and partial unknown-price semantics; model default unchanged.

[ASVS scope](asvs-scope.json):125 local change reviews and1 primary contribution.
[Protected fields](asvs-protected-fields.json): all253 requirement identities, baseline,
accountable owners and N/A fields unchanged. No whole-norm closure or production L2 claim.
Production secrets, retention, load/soak and real billing reconciliation remain future gates.
[Docker/WSL version review](host-version-review.json): update recommended, no upgrade installed;
exact relation to observed Engine/IPC faults not established.

## Rejected/interrupted candidates

[Candidates](candidates/browser-startup-failed.log) are retained separately and never added to
passing totals. SQLAlchemy numeric JSON binds, Windows CRLF Redis health and an implicit
record_active float/numeric boundary were corrected. A lower active-run cap initially gated
completed SDK compatibility records; only active admission/reactivation now consumes capacity.
The former tenant-wide invalidation row blocked independent source transactions; per-object
committed version sums now cover concurrency, reverse commit order and tenant ownership moves.
The independent research15 / per-action verification3 contract replaces the old single slot.

A backend candidate passed389 and failed10 hardened unit fixtures that inherited integration
plaintext Redis settings. Fixtures now isolate cache settings; existing HTTP/MFA/privacy/429
assertions are preserved, plus three Redis hardened startup negatives. No TLS policy relaxed.
The final backend passed402; its following browser startup candidate passed21/failed1 while
129 preceding backend fixture jobs drained. [Timing metadata](browser-startup-candidate.json)
records this rejected candidate. A read-only test-only queue drain precedes the accepted22-case
browser rerun. Existing assertions/timeouts and application source remain unchanged.

The additional Redis TLS probe initially read the repository .env alongside explicit lab secret files;
`_env_file=None` now restricts that probe to lab configuration. Application settings and TLS policy
were unchanged. Its failed candidate is retained separately.

Docker Engine500/no-route interrupted startup candidates; already-authorized Desktop recovery
preserved stale IPC separately and did not reset data/settings or delete volumes. Full dev
services were quiesced for memory bounds; unrelated projects were not individually stopped.
Private lab keys, backups and Playwright traces remain ignored; artifact checks export no values.

Canonical runners: `scripts/test-full-f15.ps1`, `scripts/test-full-f15-tls.ps1`,
`scripts/test-full-f15-redis-restart.ps1`, `scripts/scan-full-f15-security.ps1`.
Independent ignored dev/test Redis credentials: `scripts/setup-full-f15-cache.py` / `--test`.
