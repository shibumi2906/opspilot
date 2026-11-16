# F20 Jira runtime evidence

Full release acceptance remains open. Reports from failed attempts are retained;
unknown external operations are never redispatched.

The runtime implements manager-backed Jira credentials, trusted project/field
mapping, exact signed grants, durable one-attempt PostgreSQL receipts, independent
read verification, and operator reconciliation including late duplicate detection.
The main Full database remains schema0019. These tests use separate schema0023 labs.

Historical measured results from 15 November:

- [315 unit tests](runtime-units.xml).
- [Eight native MCP/PostgreSQL/vendor-stub boundary tests](runtime-boundaries-final.xml).
- [Existing sandbox receipt replay and marker checks](live-existing-replay.json):
  zero new POSTs and zero duplicate markers. Expired issue replay was denied;
  comment replay returned the saved receipt.
- [Original interrupted backend regression](backend-regression.xml): 401 passed,
  16 failed, 40 skipped. This is not a successful regression.

Continuation on 16 November:

- Readiness now accepts the two Jira migrations, with seven unit cases covering
  supported, old and unknown schemas. The original API could not become healthy
  on schema0023. F21 subprocess health checks use the same endpoint.
- [Reused r1 regression](backend-regression-20261116T061400028.xml): interrupted
  after 339 passed, 18 failed, 34 skipped. Accumulated nonterminal runs plus inherited
  F22 admission limits caused RUN_ADMISSION_LIMIT. No receipts or runs were deleted.
- [Fresh r2 full regression](backend-regression-20261116T061723073.xml): 602 passed,
  1 failed, 71 skipped in 708.51 seconds. The reject diagnostics test timed out while
  waiting for command.process telemetry. This report is not green.
- [Separate observability recheck](backend-regression-20261116T063028585.xml):
  all five tests passed in 25.14 seconds. No test deadline was widened. The initial
  timeout has not been assigned a confirmed root cause.
- [Fresh r3/subnet66 full regression](backend-regression-20261116T063232858.xml):
  **603 passed, 71 skipped, zero failures** in 675.94 seconds. It used the newly built
  f20 images without simultaneous image builds. The eight native Jira boundary tests,
  four F21 tests and seven readiness cases ran without skips or failures. Dedicated
  profile tests remain skips; this is not whole deployment acceptance. Neither r2 nor
  r3 enrolls real Jira credentials. r3 was stopped with its volumes retained.

Mypy passed for 159 source files; source/tests and the new preparation/refresh/audit
scripts pass Ruff. The UI TypeScript/Vite build passed. Scoped artifact scanning found
zero known private-value matches across 73 candidate artifacts and six r3 log streams;
no JWT-shaped values were found in those logs. All 253 ASVS backlog records are unchanged.
These checks do not constitute complete ASVS L2 verification.

Private manager tokens and recovery material remain ignored. The explicit
refresh helper preserves manager ACLs and signing keys and sends no Jira requests.
The original r1 live lab, its volumes and all unknown operations are retained.
