# F22 35,000-token budget probe on 2026-11-13

F18 repetition 1 and F22 repetition 1 both passed in that order on
`gpt-6.1-sol` with low reasoning. The same frozen scenarios and prompt were
used. The diagnostic runner raised the per-run budget to 35,000 only for
these two repeats. Its isolated test database accepted that budget through
the same reservation check used previously. The application default and
ordinary settings cap stayed at 30,000. The separate daily guard used the
owner-confirmed allowance of 200,000 tokens.

| Repeat | Reservation at reason | Actual usage at reason | Actual usage for run |
| --- | ---: | ---: | ---: |
| F18 repetition 1 | 20,310 | 5,072 | 15,874 |
| F22 repetition 1 | 20,091 | 5,227 | 16,003 |

Both final-analysis reservations matched the amounts denied in real-r5.
Both were admitted and completed in this probe. The reports correctly
preserved the unresolved conflict, so each had the expected partial outcome,
passed its assertions and recorded zero writes. This confirms the per-run
reservation as the cause of the measured failures for these repeats.
[Raw results](real.json) and [token ledger](token-ledger.json).

The API reported 29,451 input and 2,426 output tokens across 14 requests,
totaling 31,877. All requests reported usage, and the daily guard did not
stop dispatch. Billing was not independently verified.

The two results are separate diagnostics. The canonical schedule retains
its historical 90 results and 78 passes. F14 was outside this probe.
Nineteen focused local tests and Ruff passed. The source hashes, prior
report hash, ledger totals and schedule were verified. MVP isolation
passed before and after, and the lab services were stopped.
