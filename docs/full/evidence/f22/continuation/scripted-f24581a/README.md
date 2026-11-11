# F22 regression on 11 November 2026

The run checked `f24581a97f934eb87e580b8e2f0945167bd698c9` in the isolated
`opspilot-full-test-f22-nov11` project on subnet 47. All 50 scripted scenarios
passed. The report records zero unsupported facts, false successes, forbidden
calls, unauthorized writes, duplicate writes and writes before a decision.
All seven recorded ticket writes were expected by the test scenarios.
[Scripted results](scripted.json).

The separate MVP regression passed 12 of 12. All 284 Linux unit tests passed.
The 20 focused host tests passed,
including provider results at the token limit and denials before dispatch.
Ruff passed and mypy passed on 154 source files with a fresh cache.
[MVP regression](mvp-regression/scripted.json), [unit suite](units.xml),
[process exits](exits.json), [MVP isolation](mvp-after.json). The test services
and their dedicated manager were stopped after the checks.

Offline verification of the three historical real reports confirmed 53 of 90
recorded runs, 44 passes and nine failures. The 37 remaining runs begin with
F30 repetition 3. The operator confirmed a renewed free allowance. Automatic
approval review rejected the proposed real-r4 launch because it required
explicit consent to transmit the synthetic evaluation data to OpenAI.
No real-r4 report or quota claim was created.

The proposed continuation uses `gpt-6.1-sol` with reasoning `low`, up to
200,000 tokens, and `https://api.openai.com/v1/responses`. The request body
contains the repository prompt, synthetic scenario requests, response schemas
and read tool definitions. Later calls may include synthetic fixture names,
IDs, monitoring observations, incidents and runbook excerpts from the local
test database. The provider uses the local API key in the authorization header.
The client sends `store: false`. Source inputs are [the frozen corpus](../../../../../../src/opspilot/evals/full-cases.json)
and [the synthetic fixture data](../../../../../../src/opspilot/fixtures/base.json).

F22 remains blocked. The real continuation, human review and other open release
checks retain their prior status. No external provider calls occurred during
this regression.
