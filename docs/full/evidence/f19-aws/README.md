# F19 authorized AWS staging — 7 November 2026

This supplements accepted historical [local F19 evidence](../f19/README.md); it does not
replace it. Actual owned staging services were measured over HTTP by an independent
observer and scraped by real pinned Prometheus on AWS il-central-1. Readiness performs
actual disk write/read/fsync. These are observed staging measurements, not customer data.

- [Deployment](deployment.json): one t3.small, encrypted20GiB gp3, IMDSv2, no instance role,
  operator-only SSH/HTTPS8443, no outbound SG rules, verified TLS and independent SSH pin.
- [Initial healthy](initial-healthy-smoke.json), [actual replica stopped](unavailable-smoke.json),
  [recovered healthy](healthy-smoke.json): three separate passing full smoke runs, each
  including scoped native API/MCP, invalid auth, cross-tenant rejection, foreign/absent,
  stale and partial unknown, unknown credential expiry. Counts overlap; not extra unit cases.
- [Browser](browser.json): one passing real OIDC/scripted investigation, observed:staging
  provenance, actual observed health samples, no delivery-event relabel, cost0/no action,
  durable evidence preserved after refresh.
- [Cleanup](cleanup.json): tagged inventory zero, instance terminated, EBS/ENI removed.
- [Preserved previous project](mvp-isolation.json): source/env184, branch/HEAD, images,
  volume metadata and read-only content fingerprints unchanged.
- [ASVS protected baseline](asvs-baseline-check.json):253 identities/fields preserved;
  whole ASVS L2/Pilot remains NOT_MET. [Artifact secret check](artifact-secret-check.json)
  covers actual local Basic, manager, TLS, SSH and inherited credentials, values withheld.

Scope: SEC-09 upstream TLS/egress/auth/query/cardinality/range/tenant safeguards and
common SEC-01/10 provenance, isolation and secret gates. Separate lab project
opspilot-full-test-f19-aws-r1/schema0020 used accepted images without rebuilding;
main Full remains F18/schema0019. Lab stopped; volumes retained. No F20, production,
paid LLM, vendor mutation or push. Manager permission is an exact read-only credential path.

Validation: `scripts/test-full-f19-aws.ps1 -Action Smoke` three times with actual remote
replica stop/restart; OIDC browser spec passed via compose run on the running lab.
Python Ruff/compile and web TypeScript passed. Runtime binary SHA matches accepted binary.

Limitations: first native attempt failed bounded transport. After restoring Docker,
scoped native/MCP runs passed. Two browser attempts immediately after container recreation
completed with dependency read failures; the subsequent warm-contour attempt passed.
These failures are retained here, not counted as passes or reliability acceptance.
Transport budgets were not loosened. Runner now performs a connector readiness smoke
before browser; this final runner ordering was statically checked, not redeployed after cleanup.
F21 load/soak remains outside scope. The endpoint has been removed and cannot be reused
without fresh explicit resource authorization. Root CLI was logged out after cleanup.

Cost: estimate before credits for compute/disk/IPv4 is at most~USD0.152 from launch to
verified cleanup; excludes traffic/API/tax extras. It is not a final AWS invoice.
All existing project resources/consumption remain separate. Owner ceiling wasUSD5/24h.
Stage commit subject: `feat(full): verify F19 authorized AWS staging and cleanup`.
