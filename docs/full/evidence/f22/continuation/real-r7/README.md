# F22 remaining diagnostic repeats on 2026-11-13

All five repeats passed their scenario assertions on `gpt-6.1-sol` with
low reasoning. The original corpus and historical 90-run report are
preserved. [Raw diagnostic results](real.json).

| Repeat | Run token cap | API tokens | Outcome |
| --- | ---: | ---: | --- |
| F14 repeat 1 | 35,000 | 15,861 | Expected partial report with conflicting evidence |
| F14 repeat 2 | 35,000 | 15,799 | Expected partial report with conflicting evidence |
| F14 repeat 3 | 35,000 | 15,754 | Expected partial report with conflicting evidence |
| F40 repeat 2 | 30,000 | 612 | Expected exhaustion of the one-attempt budget |
| F50 repeat 3 | 30,000 | 15,032 | Expected partial report |

All three F14 repeats completed the final analysis. F40 accepted the model's
classification this time and then stopped at its intentionally configured
one-LLM-attempt limit. Its previous invalid time window did not reproduce.
F50 completed within the shared daily allowance. All five DB checks
recorded zero ticket writes.

The launcher verified and deducted the 31,877 tokens already used by real-r6
before allocating a segment limit of 168,123. This segment used 63,058
tokens across 29 requests. All requests reported usage. Combined known
usage was 94,935 out of 200,000, leaving 105,065. Billing remains
independently unverified. [Token ledger](token-ledger.json).

Ruff and 19 focused unit tests passed. The canonical report hash, recorded
diagnostic order, run budgets, source hashes and ledger totals were verified.
MVP isolation passed and the test services were stopped.
[MVP isolation](mvp-after.json).

All twelve historical failures now have a passing diagnostic repeat across
real-r5 through real-r7. The canonical report remains 78/90 because it
retains the original results. The diagnostic repeats alone do not close the
remaining F22 release gates.
