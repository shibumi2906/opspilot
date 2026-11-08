# OpsPilot Full continuation

- Work in this checkout: C:/Users/user/Desktop/code/Ops, branch codex/opspilot-full.
- Read START-HERE.md, OpsPilot_Full_Project_Specification.md and docs/full-version-status.md first.
  The tracker is authoritative; F01–F19 are done. F20 is blocked, real Jira checks deferred
  by the owner. F21 was explicitly authorized separately; see its local evidence/blockers.
- Implement only the stage explicitly requested by the user. Completion of a stage does
  not authorize starting the next stage, paid calls, external writes, production deployment or push.
- Preserve the Portfolio MVP checkout at C:/Users/user/Desktop/code/AI Incident & Operations Agent:
  tracked files, .env, branch/HEAD, images and persistent volumes. The ignored workspace locator
  may be updated when relocating Full. Run the existing isolation gate before builds/migrations.
- This repository has independent Git storage. Read mvp_path from
  .tools/opspilot-full-workspace.json or pass -MvpPath explicitly; do not infer MVP from .git.
- Use only compose.full.yaml and the opspilot-full project for dev. Test profiles require a
  separate opspilot-full-test-* project. Never run inherited MVP setup scripts in this checkout.
- The original Full worktree is a preserved source/reference. Do not run two copies against the
  same opspilot-full project or delete the old checkout while any bind mounts still reference it.
- Credentials, local private keys, cache secrets, TLS lab state and backups are ignored local
  files. Never print, commit or upload them; preserve existing keys instead of rotating at setup.
- F16 acceptance is documented under docs/full/evidence/f16; earlier stage evidence remains historical. New work needs its own scoped
  checks and evidence; do not overwrite historical reports merely for workspace checks.
- Include the stage's ASVS/SEC work plus common SEC-01/10 checks. Preserve all 253 protected ASVS
  identities/owners/baseline/N/A fields. Local scoped gates do not imply full L2 compliance.
- Keep LLM_MODE=scripted for local/CI checks unless real mode is explicitly requested. No paid
  calls, vendor writes or remote CI by inference. Stage results get a separate local commit.
- Docker Desktop was updated to 4.97.0 (Engine 29.9.2). Read local host status under .tools.
  The unrelated pinui-rag API references deleted VEKTOR.BD files; do not recreate that project.
- F17 PostgreSQL changes libc. Never mount preserved opspilot-full_pgdata into the new
  runtime. Existing Full requires compose.full.f17-local.yaml and FULL_F17_PG_VOLUME
  selecting its verified logical restore. See docs/full/f17-operations.md.
- Manager service tokens expire in one hour. Explicit setup --local refreshes dev tokens
  while preserving keys; test state is separate. Managed workers have no file grant keys.

- F17 local scripted Core acceptance is under docs/full/evidence/f17. Full Pilot and
  complete ASVS L2 remain NOT_MET. Preserve historical reports and use scoped evidence.

- F18 acceptance is under docs/full/evidence/f18. Main Full schema is0019_adapters; normal dev
  requires compose.full.yaml + compose.full.f17-local.yaml + compose.full.f18-local.yaml.
  Explicit setup-full-f18.py --local refreshes short-lived manager tokens while preserving keys.
  The default adapter registry is empty; synthetic simulator is an optional profile. No vendor/live gate.
- The observation worker has only an ingress DSN; keep business/MCP/manager credentials and key
  mounts out of it. New enrolled tenants require trusted RECOVERY_TENANTS and exact manager ACL.
- F18 regression keeps negative-fencing backend fixtures intact and uses a fresh browser/process
  project. Run labs serially on this16GiB host; automatic Docker address pools are exhausted.
  Dedicated subnet21 is F18 transport,22 optional Full simulator,23 native TLS; check overlap.
- Full Pilot and complete ASVS L2 remain NOT_MET. F19–F24 require a new user request; no push.

- F19 local evidence: docs/full/evidence/f19. User explicitly deferred authorized staging, so F19
  overall stays blocked; do not infer F20 authorization. Native synthetic Prometheus is not live.
- Main Full still F18/schema0019; schema0020 is test-only. F19 app/tests/prometheus:f19 tags are
  separate; do not implicitly rebuild/reseed/migrate dev. See docs/full/f19-operations.md.
- F19 final native subnet25; retained initial draft lab24 must not be used as accepted evidence.
  Local Prometheus is checksum-pinned3.16.0 with x/net0.62.0, static discovery, no promtool/UI.
  Official image's2 HIGH were fixed; raw nonblocking findings remain visible, whole L2 NOT_MET.

- F19 AWS staging completed on2026-11-07: docs/full/evidence/f19-aws and docs/full/f19-aws-staging.md.
  Earlier deferred-staging notes are historical. Temporary EC2/EBS/VPC resources were removed.
  Cold-restart dependency errors remain documented; full L2/Pilot and F21 reliability NOT_MET.
  Main Full remains F18/schema0019; AWS lab schema0020 is stopped.

- Current owner direction (2026-11-08) supersedes historical authorization notes above:
  F20 preparation base152d59b, real Jira checks deferred; F21 explicitly requested.
  F21 isolated test schema0021 fixes worker admission lock inversion and shared enqueue pools.
  Accepted load r4/subnet30; fault profile r6/subnet32, fencing r7/subnet33;
  each has its own F21-only manager/network. Run fencing in a freshly prepared project.
  Read docs/full/evidence/f21/README.md and checks.json before continuing. F21 overall remains
  blocked on absent F20 write/reconciliation boundaries and manager HIGH CVE-2026-78661
  (x/net0.61.0, fix0.62.0); no applicability exception. Do not start F22, use Jira, push,
  rebuild/migrate main Full or claim Pilot/whole L2 from these source-mounted local tests.

- Owner direction 2026-11-08 explicitly authorized F22 despite F20/F21 blockers, overriding
  the preceding historical no-F22 instruction for this stage only. F22 local scripted50/50
  and separate MVP12/12 evidence: docs/full/evidence/f22. Overall F22 remains blocked:
  real90 runs unauthorized (paid calls forbidden), human review pending, remote CI not run,
  manager HIGH CVE-2026-78661 and F20 dispatch/reconciliation/live boundaries unresolved.
  Holdout is public/inspected, never unseen. Main Full remains0019; F22 test schema0021
  uses an independent manager/project/subnet34. No F23/F24 authorization, no push.

- Latest F22 continuation: owner selected gpt-6.1-sol/low and stated a200000 free-token
  allowance, then requested completion. Free-quota real execution is intended, but paid
  overage remains forbidden. See docs/full/evidence/f22/continuation: Full .env key/model
  absent at preflight; account/project/model eligibility and unused quota await confirmation.
  New eval-only cumulative token guard and exclusive private quota claim must precede real
  dispatch. Never reset a claim/unknown ledger to obtain another allowance or copy MVP keys.
  F20/F21/security/human/remote-CI blockers remain; historical reports are not overwritten.

- Latest F22 real evidence supersedes missing-key/quota notes: owner confirmed model
  eligibility/200000 unused tokens and saved Full credentials. See continuation/real-r1:
  27/90 recorded,23passed,186340 known tokens across114 calls;63 unexecuted.
  GLOBAL_TOKEN_LIMIT denied next reservation. Preserve private authorization/ledger;
  no fresh allowance or resume inferred. F14x3 failed budget/conflict; F15repeat3
  UnboundLocalError root cause open. F22 blocked; human/F20/F21 HIGH/CI still open.
