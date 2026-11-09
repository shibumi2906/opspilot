# F22 continuation on 2026-11-09

The owner confirmed a fresh allowance of 200,000 complimentary tokens for the
same project and model. With `gpt-6.1-sol` and low reasoning, the harness continued
after the 27 recorded runs in [real-r1](../real-r1/README.md).

The second attempt recorded 13 runs, of which 10 passed. Cumulative results are
40/90 recorded, 33 passed, 7 failed, and 50 unexecuted. The ledger records 92
provider attempts with known usage: 171,917 input and 13,264 output tokens, totaling
185,181. The next reservation did not fit the remaining 14,819 tokens. Actual
billing is independently unverified.

New failures are F18 and F22 for outcome and evidence conflict, and F24 for missing
approval action, outcome, required tools, action count, and expired credential
evidence. The harness recorded the missing action explicitly. Historical failures
remain in cumulative accounting, and no scheduled repetition was replayed.

[Report](real.json) · [Quota ledger](token-ledger.json) · [MVP check](mvp-after.json)

F22 remains blocked. The incomplete real schedule and recorded failures, pending
human review and remote CI, F20 deferred Jira and incomplete write/reconciliation
boundaries, and F21 manager HIGH CVE-2026-78661 remain open. F22 services were stopped
and MVP fingerprints matched. The current launcher supports the first continuation
only. Further continuation requires consuming the two reports as one verified
schedule prefix, plus a newly confirmed allowance.
