# F19 — local Prometheus connector; staging gate open

Base61dfdfd; independent Ops checkout, branch codex/opspilot-full. The user explicitly authorized
the local part and deferred staging. **F19 overall is blocked**, not done: no separate authorized
staging endpoint/credentials were supplied. Full Pilot and whole ASVS L2 remain NOT_MET.

[Checks](checks.json), [contracts](../../f19-security-contracts.md),
[operations](../../f19-operations.md), [actual local version/scope](prometheus-smoke.json).

## Verified local behavior

- Fixed job/UUID/expected-target PromQL, health + original sample timestamp in one evaluation;
  expected target pairs and freshness bounds, explicit unknown for absent/stale/partial data,
  credential expiration unknown. Bounded adaptive range, cardinality/body/time/response limits,
  deterministic sample identities and persisted breaker; no fixture fallback for configured sources.
- Operator registry and immutable mapping, exact manager credential refs and metadata, unique
  connector credentials, native HTTPS Basic Auth, all-answer DNS validation/numeric pinning,
  verified hostname/CA, no redirect/proxy/compression/free query or write endpoint dispatch.
- Schema0020 adds bounded immutable mapping and forbids Prometheus ingress. Tenant-bound boolean
  function is limited to workflow/domain roles. Configured source preconditions cannot fall back
  to synthetic monitoring to authorize writes. Existing MCP13, DTO1, graph v1/v2 contracts remain.
- Metric samples retain synthetic provenance in canonical facts and UI; they are not labeled as
  delivery events. Native Prometheus Basic Auth has no label-level RLS: MCP/RLS/selector/response
  controls enforce local tenant mapping; upstream staging isolation/gateway review remains required.

## Measurements

- Fresh no-binding legacy regression:527 passed,74 dedicated skips,982.35s
  (`.tools/f19-regression-final.log`; [image snapshot](regression/images.json)). The skipped30 F19
  cases run in the dedicated profile;44 inherited specialized/F18 cases retain their earlier gates.
- Final native profile:287 passed/0 failed in76.06s (`.tools/f19-native-patched-final.log`):257 unit
  (200 inherited +57 F19) and30 actual engine/HTTP(S)/manager/DB/MCP contract cases. These counts
  overlap with the broad regression and must not be summed into a unique-test total.
- Actual pinned Prometheus3.16.0, source e2e28adeee2c5883d000fc82aca6008cfbf7e96d/Go1.27.3 with x/net0.62.0; see [remediation](../../f19-prometheus-image.md).
  Synthetic exporter + separate real HTTPS fault server. Native absent/partial/healthy/unavailable,
  sample staleness (engine lookback retains old sample), API cardinality limit,401/403/429/5xx,
  redirect, slow/drip/oversize/compressed/duplicate JSON/warnings/infos, TLS/DNS/query boundaries,
  exact manager ACL, tenant isolation, immutable/read-only mapping and breaker are exercised.
- [Real OIDC browser](browser.json):1 passed,0 skipped,0 flaky; UI investigation obtains metric
  samples/status through MCP, shows synthetic provenance and unknown credential status, preserves
  evidence on refresh, proposes no action and reports zero model API cost.
- [Installed source match](source-image-match.json):150 app,81 test Python files,21 migrations and
  unchanged Nginx. Ruff/format231 files and mypy150 files pass. Final native snapshot covers the
  Prometheus/parser/fixture/fact-formatting refinements after the no-binding regression snapshot.
- [ASVS preservation](asvs-baseline-check.json):all253 inherited rows/fields/owners/baselines/N/A
  unchanged;85 scoped contributions and5 primary local reviews; zero whole-requirement closure.
- [Current-secret artifact check](artifact-secret-check.json) and [bounded runtime log/mount check](runtime-secret-check.json):
  no credential/private-key matches;31 containers,13 application mount checks. Operator material
  stays out of app mounts. Final app/Prometheus raw HIGH/CRITICAL0; Python/npm audits pass. Original Prometheus2 HIGH were fixed by pinned source rebuild/x-net0.62.0; see image remediation. Raw app MEDIUM(zlib) and Prometheus UNKNOWN(x/crypto) remain visible; no whole L2 claim.

## Preservation and limits

[Inventory](inventory.json) verifies all6 accepted F18 image tags unchanged. Main Full remains
schema0019, ready; no F19 dev migration or seed. Test schema0020 and app/tests:f19 tags are separate.
[Final MVP isolation](mvp-final.json) preserves184 tracked/env files, branch/HEAD, images, volume
metadata and read-only content. All test profiles stop with data retained. No paid calls, vendor
writes, production deployment, remote CI, push or F20 work.

Earlier failed attempts remain in ignored logs: initial migration omitted domain EXECUTE for the
tenant binding check and safely rejected legacy writes; fixed minimally and rerun on a fresh DB.
A unit/integration basename collision was corrected. Initial TLS setup had a CA-equal leaf subject;
verification rejected it. The leaf was repaired with both keys/CA preserved, without weakening TLS.
Review also corrected the inherited delivery-event fact label for metrics; final unit and real UI
checks cover it. Duplicate host unit attempts were interrupted and are not accepted measurements.

Staging completion needs its own authorized endpoint, tenant mapping/expected targets, least-privilege
access and CA/address policy, upstream tenant isolation review, actual version and redacted MCP/UI
smoke. Generated local series are never live/customer evidence. F21 load/soak, F22 real/holdout,
F23 production network/recovery and independent full ASVS reviews remain future gates.
