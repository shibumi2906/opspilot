# Local F19 operations and deferred staging

F19 source/schema0020 is validated in independent test projects using app/tests:f19 tags.
The ordinary `opspilot-full` runtime remains accepted F18/schema0019 with its verified logical
PostgreSQL volume. No F19 migration, seed or customer mapping is applied there. Default registry
stays empty. Rebuilding dev against0020 without an explicit preservation/migration plan is not
part of this local acceptance. Never attach the original Full PG volume to a different libc.

Run from `C:/Users/user/Desktop/code/Ops`, scripted only. Labs run serially. Preserve existing
test projects/volumes and choose a fresh project for changed PostgreSQL runtime or fresh backend
fixtures. The runner checks MVP before builds and explicit subnet overlap before creating networks.

```powershell
# Broad regression on a fresh DB; requires exclusive use of the shared test-manager network.
./scripts/test-full-f19-regression.ps1 -Project opspilot-full-test-f19-regression-r1
# Native local Prometheus + actual fault transport/manager/DB/MCP + dedicated real-OIDC browser.
./scripts/test-full-f19.ps1 -Project opspilot-full-test-f19-local-final -Subnet 25
# New runtime/fixture image and package audits, separately after the test profile stops.
./scripts/scan-full-f19-security.ps1
.venv/Scripts/python.exe scripts/check-full-f19-asvs.py
.venv/Scripts/python.exe scripts/check-full-f19-secrets.py
```

Subnet24 was used for the retained initial lab;25 for final local acceptance. Do not delete
networks to obtain an automatic pool. `-StartOnly` prepares a serial lab for diagnosis; stop
only that project afterward. Prometheus has no host-published port, read-only root, bounded RAM,
tmpfs TSDB, native TLS/basic auth, no admin/lifecycle/remote-write flags, 1h fixture retention,
query concurrency4/sample2000/timeout1s. Exporter metrics are generated and explicitly synthetic.
The fixture image is rebuilt from checksum-pinned upstream3.16.0 with x/net0.62.0, static discovery
and no promtool/embedded UI after the official image failed the HIGH gate; see
[image remediation](f19-prometheus-image.md). This is a test server, not a vendor deployment.
The HTTPS fault server is a separate synthetic contract fixture, not the Prometheus engine.

Setup via pinned ephemeral bcrypt5.0.0 preserves existing PKI and passwords, bootstraps/unseals
the existing test OpenBao, and replaces only its1h service tokens. No app dependency or uv.lock
change is required. Ignored .tools/f19-private holds operator material; f19-server holds only lab
server material; f19-client contains CA/registration and scoped MCP token; f19-probe contains
test-control values. Applications never mount recovery shares, root token or CA private key.
API receives registration/CA only; MCP receives read-only credential token; workers receive
existing grant-manager credentials, no connector token. Logs/evidence must remain value-free.

Staging is deliberately open per the user's instruction. To resume: supply a separate authorized
HTTPS target and a local protected access file, exact tenant/customer/integration/connector UUIDs,
expected target names and metric semantics, deployment/dataset declaration, CA and permitted IPs,
least-privilege Basic/bearer credential and approval reference. Store credential only under its
computed manager path. Review immutable mapping and tenant header before enrollment. Verify actual
build version, scoped results and unknown/error cases, then UI/MCP smoke; save redacted evidence.
This document provides no permission to call a customer endpoint, deploy production, write to a
vendor, invoke a paid model, push or start F20.
