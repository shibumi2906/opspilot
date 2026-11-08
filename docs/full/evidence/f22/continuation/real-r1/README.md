# F22 real free-quota attempt

2026-11-08, base `2e06498`. Owner confirmed gpt-6.1-sol eligibility and
200,000 available complimentary tokens, saved Full credentials and authorized
execution. Normal configuration remained scripted; real mode was command scoped.

The fixed schedule stopped at the cumulative reservation guard: **27/90 recorded,
23 passed, 63 unexecuted**, covering15/50 distinct cases. All114 dispatched provider
calls have known usage:174,237 input +12,103 output = **186,340 tokens**. The next
reservation did not fit the remaining13,660; no further call or fresh allowance
was attempted. The private authorization claim remains preserved. Billing itself
is not independently verified; the catalog's zero cost is not evidence of zero
actual billed spend.

F14 failed all three scheduled holdout repetitions with OUTCOME/EVIDENCE_CONFLICT
after per-run investigation budget exhaustion. F15 repetition3 recorded
EXECUTION_UnboundLocalError at the global stop boundary; its root cause is not
established. It remains failed, with no invented report/DB assertions. DB/metric
denominators are26. No tuning, fourth holdout repetition or best-of selection.

The measured cases show0 unsupported facts, false success, forbidden calls,
unauthorized/duplicate/pre-decision writes;3 approved ticket writes. This is
incomplete evidence, not acceptance of the full security or workflow matrix.

See [raw report](real.json), [ledger](token-ledger.json), [checks](checks.json),
[pending human review](human-review.json), [preflight](preflight.json) and
[secret scan](secret-scan.json). Human judgments remain null. Historical scripted
and earlier continuation reports remain intact. Holdout remains inspected/public.

MVP fingerprints passed before and after. Only retained F22 services and its own
manager were explicitly started/stopped; no build/migration/seed was performed.
Docker Desktop startup automatically resumed unrelated containers according to
their existing restart policies; no explicit main Full start was issued.
F22 containers are stopped; images/volumes/networks remain preserved.

F22 overall **blocked**, real gate **NOT_MET**. Human review, incomplete/failed real
schedule, remote CI, F20 dispatch/reconciliation/deferred Jira and F21 manager HIGH
CVE-2026-78661 remain open. Full Pilot/whole ASVS L2 NOT_MET. No push or Jira calls.
