# F22 local eval evidence

2026-11-08, `C:/Users/user/Desktop/code/Ops`, `codex/opspilot-full`, base `e1674e6`.
Owner explicitly authorized F22 separately despite F20/F21 blockers. **F22 blocked,
not done**. [Machine-readable gates](checks.json), [contracts](../../f22-eval-contracts.md).

Latest [free-quota continuation](continuation/README.md): cumulative200000-token guard,
fresh scripted50/50 and11 unit guards. Real remains unexecuted because Full credentials
and model were absent and free-quota eligibility/remaining balance was not confirmed.
The original evidence below is historical and preserved.

| Gate | Measured outcome |
| --- | --- |
| Full scripted | [50/50](scripted.json), exactly 50 distinct identities, 30 dev / 20 holdout |
| Separate unchanged MVP regression | [12/12](mvp-regression/scripted.json) |
| Eval negative/accounting/authorization guards | [JUnit](unit.xml) |
| Mixed-plan outcomes/dependencies/cancellation | [Separate regression](mixed-regression.xml), excluded from 50 |
| Real/holdout | [Blocked](real-holdout.json), 0/90 runs, no paid/model/vendor calls |
| Human claims/hypotheses review | [Pending queue](human-review.json), no human acceptance claimed |
| Remote CI | Not run; manual workflow and ephemeral initializer prepared |
| Security | [NOT_MET](security/checks.json), one manager HIGH, no applicability exception |
| ASVS inherited baseline | [253 complete rows unchanged](asvs-baseline.json), whole L2 NOT_MET |
| Secrets/config/static | [Secret scan](secret-scan.json), [config](config-gates.json), [static](static-checks.json) |
| MVP | [Before](mvp-before.json) / [after](mvp-after.json), preserved |
| Cleanup | [Owned lab stopped](cleanup.json), images/networks/volumes retained |

Corpus: 10 lookup/status, 12 investigation, 8 approval, 8 policy/injection/access,
6 infrastructure, 6 ambiguity/insufficient data. Split and corpus SHA256 were fixed
before execution in `src/opspilot/evals/full-split.json`. No prompt tuning occurred.
Holdout was publicly inspected during harness implementation/debugging and **is not
unseen**. These cases reuse bounded synthetic fixtures and do not estimate production
distribution quality. First pass and repeats have explicit denominators; real schedule
is 30+20×3=90, not110. No best-of selection or invented real report.

Accepted [scripted report](scripted.json) contains all snapshots, source IDs/types,
LLM read selection separately from verification reads, per-action outcomes, durable
job state/attempts, canonical claim predicates and direct DB checks. Setup errors,
usage, unknown usage, actual spend, prompt/fixture/corpus/lock/dependency/source and
harness hashes are recorded. Scripted provider consumption/spend is zero. Canonical
claim checks are not a substitute for the pending human review.

HTTP uses ASGI BFF transport with actual session/CSRF middleware and roles; sessions
are test fixtures. Worker claim/execute/finish is in process, MCP uses native TCP and
real DB roles/RLS/Redis/manager. No new process-isolation or IdP-login acceptance is
claimed. Two tenants, RU/EN, distinct operator/approver, authorization/CSRF probes and
exact ticket verification are exercised. The 50 cases use v1 single-ticket workflows;
v2 mixed per-action behavior is separately regressed, not counted as extra eval cases.

The lab `opspilot-full-test-f22-r1`, subnet34, schema0021, has its own TLS manager and
private ignored state. Existing F19 images plus current read-only source mounts are
used; no release image was built. Main Full remains F18/schema0019 without restart,
rebuild, seed or migration. MVP source/env/media/head/images/volumes remain preserved.

Failed/diagnostic [attempts](attempts) remain visible. The first partial run read
checkpoints without the persisted operator identity: RLS correctly hid them, and the
harness failed. Diagnostic2 verifies the correction through existing `execution_scope`;
no RLS/fence/timeout was weakened. r2 passed50/50 before final reporting/provenance
enhancements; `scripted.json` is the fresh final50/50 run. Diagnostic limits always
produce incomplete failed gates. Raw harness stdio remains ignored under `.tools`,
scanned for exact local secrets/JWT shapes; removed --rm container logs cannot be
retrospectively scanned. Retained service logs are selected by exact F22 project labels.

Fresh Python audit:0 known vulnerabilities. App/PostgreSQL/Redis:0 HIGH/CRITICAL.
Manager: **HIGH CVE-2026-78661**, x/net0.61.0, fix0.62.0. Raw scanner reports and
archive-config/image-ID verification remain visible. No manager rebuild, image/volume
pruning, applicability exception or F21 completion is claimed.

F20 write/one-attempt/reconciliation is incomplete; real Jira checks remain explicitly
deferred. F21 functional checks passed but overall remains blocked on those boundaries
and manager HIGH. F22 cannot supply the missing external-write evidence and does not
close either stage. Real eval authorization, human review, remote-CI execution and
security acceptance remain absent. Full Pilot/whole ASVS L2 **NOT_MET**. F23/F24 not
started. No push, remote CI, paid calls or vendor calls.
