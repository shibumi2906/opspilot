# F22 continuation on 2026-11-10

The owner confirmed a new daily allowance of 200,000 complimentary tokens.
The run used gpt-6.1-sol with low reasoning and continued the verified 40-run
prefix from real-r1 and real-r2. It recorded 13 new runs, with 11 passes.
Cumulative results are 53/90 recorded, 44 passed, 9 failed and 37 unexecuted.

All 91 dispatched calls reported usage: 170,485 input and 15,692 output tokens,
totaling 186,177. GLOBAL_TOKEN_LIMIT denied the next reservation because the
remaining 13,823 tokens could not cover it. Actual billing remains unverified.

New failures were F25 repetition 2 and F30 repetition 2. Both lacked an expected
approval action and failed outcome and tool checks. See [raw results](real.json)
and the [quota ledger](token-ledger.json).

MVP fingerprints matched before and after. The isolated F22 services were stopped.
F22 remains blocked by incomplete execution, recorded failures, pending human
review and remote CI, F20 deferred Jira and incomplete reconciliation, and F21
manager HIGH CVE-2026-78661.
