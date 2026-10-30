# F16 accepted local evidence

F16 is done in Ops, base a06d1a7 (accepted F15 4733998). F17 is not started.
[Machine summary](checks.json), [complete release log](release.log),
[SEC-05 contracts](../../f16-security-contracts.md), [operator runbook](../../f16-observability-runbook.md).
Full ASVS L2 remains NOT_MET; no whole-requirement closure or production SLO/paging claim.

- Frozen backend422passed/11dedicated skips: [backend](backend-final.log).
- Final focused21: [trace/SQL/privacy/transaction tests](targeted-final.log); HTTP/journal38:
  [unit log](http-journal-unit.log). Final full regression includes the same affected code.
- Browser23, queue5, fencing3, provider-crash1, Redis outage/recreate1:
  complete release log and [process evidence](process/), [Redis state](redis-restart.json).
  The legacy API restart skip is a compatibility alias of the active durable queue gate.
- [Collector native probes](observability/collector-native.json), actual outage, tamper alert,
  paired restoration and live nginx upstream error: [fault drills](observability/fault-drills.json).
  Original/corrupt paired copies remain private under ignored .tools.
- Native profile: [TLS8](tls/tls-probes.json), [collector12](tls/collector-native.json),
  [Redis6](tls/redis-tls.json), [MFA14](tls/browser.json), [IdP policy4](tls/idp-policy.json).
- [Scripted eval12/12](evals/scripted.json): hard safety true, unauthorized writes/duplicates/
  false verified success0; no paid/provider/vendor calls.
- [Application source131](source-match.json), [UI/browser source38](ui-source-match.json).
  The final UI punctuation correction only repairs Windows UTF8 mojibake; logic is unchanged.
- [Fresh security reports](security/): app/web/Redis raw HIGH/CRITICAL0; Python/npm0.
  IdP raw4/applicable0 is retained with exact image/component/raw-report-hash proof;
  no scanner ignore, package metadata removal or risk acceptance.
- [Upgrade preservation](rollout-preservation.json):0016→0017, counts/SHA of12 legacy tables
  match before workers; only the three added command columns are excluded from old projection.
- [Live OIDC/scripted diagnostics](live-diagnostics.json), [restored dev](restored-full.json),
  [final MVP isolation](mvp-isolation.json), [ASVS253 baseline](asvs-baseline-check.json).
  All inherited owners/baseline/N/A fields stay unchanged;141scoped/16primary reviews contribute.

Important failures found before acceptance were fixed and rechecked: BusyBox printf syntax,
Windows timestamp collision in log-batch acknowledgement, workflow records displaced by SQL
detail in the100-record view, root-created key ownership, verified SQLite snapshot boundaries,
idle worker/SSE DB trace flood, and UTF8 punctuation. Error diagnostics were retained throughout.
Prototype/candidate logs remain separate; only backend-final/release/checks are acceptance.

Reproduce with scripts/test-full-f16.ps1 (explicit MVP path/locator), the separate native TLS
runner, and scripts/deploy-full-f16-local.ps1 for a preserved0016 dev database. Existing dev is
already migrated: normal startup must not reseed users/data. Only a distinct Full test project
may run the tamper/outage drill. Secrets/credentials/customer request bodies are never evidence.
