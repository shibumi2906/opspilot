# F22 diagnostic repeats and real schedule on 2026-11-12

The owner confirmed a renewed 200,000-token free allowance. The synthetic runs
used `gpt-6.1-sol` with reasoning `low` in the isolated F22 lab on subnet 49.
The report records base `629ab24` and hashes the modified harness, imported
application code and fixtures used during execution.

The ten diagnostic repeats ran in the owner's order. F25 repeat 2, F24 repeat 1,
F30 repeat 2, F39 repeat 2 and F15 repeat 3 passed. The earlier failures in
F25, F24, F30 and F15 did not reproduce, so their original causes are still
unconfirmed. F39 repeat 2 passed on the renewed quota, consistent with its
previous recorded global quota stop. [Raw results](real.json).

All five contradictory-evidence repeats failed on `reason` before dispatch.
`workflow.reserve_resource` rejects a request when settled tokens plus the
requested reservation exceed the 30,000-token per-run cap. The provider's
reservation uses the serialized UTF-8 payload size plus a 6,048-token allowance.
The first F14 was reviewed before its next repeats. [F14 review](f14-review.json).

| Run | Already used | Available | Requested | Shortfall |
| --- | ---: | ---: | ---: | ---: |
| F14 repeat 1 | 10,777 | 19,223 | 20,091 | 868 |
| F18 repeat 1 | 10,805 | 19,195 | 20,310 | 1,115 |
| F22 repeat 1 | 10,786 | 19,214 | 20,091 | 877 |
| F14 repeat 2 | 10,780 | 19,220 | 20,091 | 871 |
| F14 repeat 3 | 10,776 | 19,224 | 20,091 | 867 |

The remaining 22 scheduled identities were recorded. Twenty passed. F40
repeat 2 failed classification after the model selected an event window of
1,792,314,000 seconds, about 57 years. A read-only checkpoint inspection
reproduced the `EventsArgs` validation error against its seven-day maximum.
F50 repeat 3 was interrupted at `investigate` by the global token guard.
[F40 checkpoint diagnosis](f40-checkpoint-diagnosis.json).

The five-report chain records 90/90 scheduled identities, 78 passes and 12
failed records, including two global quota interruptions. Diagnostic repeats
have separate records. DB and metric checks cover 89 scheduled records.
They found zero unsupported facts, false successes, forbidden calls,
unauthorized writes, duplicate writes or writes before a decision.

Both parts of this segment shared one quota claim. All 108 dispatched requests
reported usage of 173,695 input and 13,053 output tokens, totaling 186,748.
The next reservation did not fit. Actual billing remains unverified.
[Quota ledger](token-ledger.json).

The 13 local tests and Ruff passed before dispatch. The exact schedule,
accounting, prior-report hashes and current source hashes were verified. The
MVP isolation gate accepted existing README-only commit `bec833b` and checked
the other historical fingerprints. The F22 test services were stopped.
[MVP isolation](mvp-after.json).

F22 remains blocked on failed real results, human review, remote CI and the
existing F20 and F21 dependencies.
