# F19 temporary AWS target

Owner explicitly approved one t3.small, encrypted20GiB gp3, one public IPv4,
maximum24h and USD5 gross, followed by removal. This authorization is limited to
F19 staging; no F20, production deployment, paid LLM or push.

`opspilot-staging` authenticates as `opspilot-staging-audit`. It intentionally cannot
provision. The owner must authenticate temporary `opspilot-admin-setup` to perform
the approved deployment. Never broaden the audit user to AdministratorAccess.

Read-only review and amounts are in ignored
`.tools/f19-aws-readonly-review-2026-11-07.md`. Current plan API balanceUSD104.85,
Free plan active until2027-03-02 or exhaustion. Credit rows totalUSD107.93; current
month usageUSD3.079538 explains the rounded difference (inference). Older existing
project consumption remains separate; net cost after credits is not zero usage.

Regional quoted base for24h: computeUSD0.576, disk approximatelyUSD0.0704 on a
30-day proration basis, IPv4USD0.12. ApproximatelyUSD0.77 excludes data/API/tax
extras and precedes credits. USD5 is an approved ceiling, not a billing hard cap.

## Prepared artifacts

- `scripts/f19-aws-staging.py prepare` creates a fresh ignored resource ledger and
  local SSH key, preserving preexisting material by refusing to overwrite.
- `provision` uses an Amazon-owned AL2023 x86_64 image, dedicated tagged
  VPC/subnet/route/IGW/security group, exactly one instance, standard CPU credits,
  encrypted root with delete-on-termination, IMDSv2, no instance IAM role,
  operator-only /32 SSH and HTTPS8443. No NAT, ALB, RDS, AMP or Elastic IP.
- Every returned resource ID is recorded. A partial deployment must be inspected
  or destroyed, never blindly re-created. AWS API timeouts may leave unrecorded
  resources; inspect the unique F19Run tag before retrying or declaring cleanup.
- Bootstrap requests guest shutdown after23h; EC2 instance-initiated shutdown is
  configured to terminate. Verify the deadline immediately after SSH is available.
  This is a fallback, not proof of actual deletion. Manually terminate after smoke.
- `destroy` checks exact ownership tags and deletes only ledger resources. Verify
  root-volume/ENI cleanup and delayed billing separately. No preexisting AWS resource
  is deleted or reused.

Accepted patched amd64 Prometheus is exported locally from the accepted F19 image
without rebuilding. Record hash and actual server build info. Keep CA private key,
SSH private key, read credential and server private key ignored and out of reports.

`infra/prometheus/staging-observer.py` provides actual owned HTTP services whose
readiness performs disk write/read/fsync; a separate observer probes those endpoints
over HTTP. Values describe measured staging health, never customer delivery data.
All application/exporter ports bind loopback. Prometheus scrapes job`opspilot`,
single explicit tenant/customer/integration labels, primary/replica expected targets.
No local generated fixture is relabeled as observed.

## Execution checklist (completed; results below)

1. Authenticate provisioner; inspect approved account, quote, limits and AMI.
2. Deploy target, pin SSH host key using independent AWS console evidence; configure
   TLS/IP SAN and Basic read auth, bounded queries/retention/resources and no admin/
   lifecycle/write API. Only the tenant-dedicated source is exposed over HTTPS8443.
3. Record explicit staging/observed registration, immutable IDs/mapping/expected
   targets, owner approval reference and computed manager credential path.
4. Use a fresh local F19 test project/schema0020. Main Full/schema0019 remains intact.
   Run MVP isolation before builds, use preserved manager keys and scripted mode.
5. Verify actual version, health, controlled service failure/recovery, absent/stale/
   partial/unauthorized/foreign-scope semantics, exact-source MCP and real-OIDC UI.
   Preserve redacted staging evidence separately from accepted historical local tests.
6. Remove staging resources within the approved window, verify inventory and record
   cost evidence. Do not mark F19 done before actual staging/MCP/UI evidence passes.

Sources: [AL2023 AMI parameters](https://docs.aws.amazon.com/linux/al2023/ug/ec2.html),
[EC2 shutdown semantics](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html).


## Result, 2026-11-07

[Acceptance evidence](evidence/f19-aws/README.md): healthy/failure/recovery MCP smoke and
real-OIDC UI passed. Strict transport budgets were retained. Two cold-start UI attempts
failed dependency reads; a warm run passed; no reliability/soak acceptance is claimed.
All created AWS resources removed and inventory verified, including root EBS and ENI.
Estimated compute/disk/IPv4 upper boundUSD0.1517 before credits and extras; final billing lags.
F19 AWS test lab stopped; preserved main Full remains F18/schema0019. F20 not started.
The local audit IAM identity remains for later read-only use; unrelated project untouched.
