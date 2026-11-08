# F22 free-quota continuation

Latest: [real-r1](real-r1/README.md) supersedes the historical missing-credentials
preflight below. Owner confirmed eligibility/200000 available tokens and saved
credentials. Real attempt stopped at the quota reservation boundary:27/90 recorded,
23passed,186340 known tokens,63 unexecuted. F22 remains blocked.

Base `8e4f44e`, 2026-11-08. Owner requested completing F22 after selecting
`gpt-6.1-sol`, reasoning low, with a stated 200,000 complimentary-token allowance.
This authorizes the intended real evaluation within the confirmed free allowance;
it does not authorize paid overage, Jira writes, push, remote CI or F23/F24.

[Preflight](preflight.json) records only credential presence, never its value.
At preflight, `C:/Users/user/Desktop/code/Ops/.env` still has an empty provider key
and model. MVP credentials were not copied and its `.env` was not modified.
Account/project/model eligibility and the unused daily free balance also await
owner confirmation. Therefore actual real runs/provider calls remain **zero**;
F22 remains **blocked**, not done. Original F22 reports remain historical and intact.

## Prepared work

- `src/opspilot/evals/token_guard.py`: eval-only cumulative conservative reservation
  over all in-process RealProvider instances. Durable reservation precedes dispatch;
  known input/output usage settles it; unknown usage retains its reservation and
  stops further dispatch. Exhaustion or model change also stops dispatch.
- The bound reuses the existing provider reservation (serialized UTF8 request bytes,
  4,000 maximum output tokens, 2,048 overhead margin). A reported bound violation is
  retained and stops later calls. This is a conservative local resource bound, not
  a server-side guarantee of free billing or an account-wide quota query.
- `tests/f22_lab.py`: real mode requires explicit authorization plus free-quota
  attestation. Ledger path cannot be reused. An exhausted/unknown quota leaves the
  remaining schedule explicitly unexecuted, rather than recording skipped cases as
  measured passes. Requested model, reasoning and ledger accompany the report.
- `scripts/run-full-f22-real.py`: reads only Full settings, leaves ordinary mode
  scripted, passes the provider key through the child environment by variable name,
  and discards no harness stdio. It refuses existing reports/logs and exclusively
  claims `.tools/f22-real/quota-authorization.json` before launch. Changing a report
  name cannot reset the owner's allowance. Launch errors do not reset the claim.
- Accounting distinguishes incomplete/failed real execution from human-review-pending
  execution. Catalog cost estimates no longer become claimed actual billed spend.
  Actual real billing remains unknown until supported by account billing evidence.
- Unit/CI entry points include quota-guard tests. Remote CI was not executed.

After the local key/model and free-quota conditions are confirmed, the prepared
operator command is:

```powershell
.venv/Scripts/python.exe scripts/run-full-f22-real.py --confirm-free-quota --report-name real-r1
```

Do not run it under unverified eligibility/remaining quota. The existing test lab
and its manager must be ready first; the command does not prepare, seed or migrate
any database. A failed/ambiguous launch requires inspecting the retained claim and
ledger, not deleting them to obtain another allowance. More quota, another day or
another run requires explicit owner direction and reconciliation of prior usage.

## Checks and limitations

[guards.xml](guards.xml) covers cumulative reservation/refund, durable-before-dispatch,
unknown-usage stop, model-change denial, owner maximum, existing ledger refusal,
multiple provider instances and exact real/holdout accounting. Host sandbox attempts
could not initialize asyncio's loopback socketpair; an explicit local unsandboxed
unit run passed without network provider calls. Docker Desktop was initially stopped;
its CLI startup restored Engine29.9.2 without building/deleting any image/volume.

[scripted-check](scripted-check/scripted.json) is a separate regression of the updated
harness, never an overwrite of the previously accepted50/50. The original12 MVP
evals and corpus remain unchanged. MVP isolation is separately checked here.

Human review is still pending; an AI-generated report is not a human judgment.
F20 dispatch/one-attempt/reconciliation and deferred live Jira remain incomplete.
F21 manager HIGH CVE-2026-78661 remains unresolved; no new applicability exception or
manager rebuild is claimed. No authorization to repair F20 or publish/execute remote
CI is inferred from “finish F22”. Full Pilot/whole ASVS L2 remain NOT_MET.
