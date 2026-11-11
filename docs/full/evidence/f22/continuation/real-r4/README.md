# F22 real continuation on 2026-11-11

The owner confirmed a renewed 200,000-token free allowance and explicitly
authorized sending the synthetic F22 evaluation data to OpenAI Responses API.
The run used `gpt-6.1-sol` with reasoning `low` on commit `4a1c40d` in the
isolated `opspilot-full-test-f22-nov11-real` project on subnet 48.

The verified 53-run prefix was retained. This segment added 15 records, with
14 passes and one run interrupted by the quota guard. Cumulative results are
68/90 recorded, 58 passed, 10 marked failed and 22 unstarted.
The next scheduled run is F39 repetition 3. Earlier results retain their
original source versions and outcomes. [Raw results](real.json).

All 91 dispatched requests reported usage. The ledger recorded 170,716 input
tokens and 14,819 output tokens, totaling 185,535. The next reservation did not
fit the remaining 14,465 tokens, so `GLOBAL_TOKEN_LIMIT` stopped dispatch.
F39 repetition 2 recorded `EVAL_GLOBAL_TOKEN_LIMIT` at `investigate`, then failed
the required-tools and evidence assertions. Its DB check found zero writes.
Actual billing remains unverified. [Quota ledger](token-ledger.json).

The four-report chain, exact schedule, ledger totals and hashes of the imported
application and fixture files were verified locally. The 15 new records all
have DB and metric checks. Across the 68 records, these checks are present for
67. Recorded invariants show zero unauthorized writes, duplicate writes,
pre-decision writes, forbidden calls, unsupported facts or false successes.

The test services and their dedicated manager were stopped. The MVP isolation
check passed before and after the run. [MVP isolation](mvp-after.json).

F22 remains blocked on the incomplete real schedule, recorded failures,
pending human review and remote CI, and the existing F20 and F21 dependencies.
