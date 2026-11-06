# OpsPilot Full continuation

- Work in this checkout: C:/Users/user/Desktop/code/Ops, branch codex/opspilot-full.
- Read START-HERE.md, OpsPilot_Full_Project_Specification.md and docs/full-version-status.md first.
  The tracker is authoritative; F01–F18 are done; F19–F24 not started.
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
