# F19 local Prometheus image remediation

The official Prometheus3.16.0 image at digest
`sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06`
failed the raw HIGH/CRITICAL gate. [Original report](evidence/f19/security/upstream-prometheus-image.json)
contains two HIGH occurrences of CVE-2026-78661: `golang.org/x/net v0.61.0` in prometheus and
promtool. The Go vulnerability database reports0.62.0 as the fixed version. No ignore or
reachability exception closes this finding.

[Dockerfile](../../infra/prometheus/Dockerfile) builds a real upstream server from the v3.16.0
source archive pinned by SHA2562709a3bd43f9d15e0cecfc33ab473d011e2a69ab29265b91398cc1b8561403c0,
using pinned Go1.27.3 and `go get golang.org/x/net@v0.62.0` with normal Go checksum verification.
Version remains3.16.0; branch identifies `f19-xnet-0.62.0`. Build module metadata ships at
`/build/modules.txt`; licenses ship at `/licenses`. The resulting image ID is recorded in inventory.

This image is exclusively the local test fixture: upstream-supported `remove_all_sd` retains
static discovery, the query engine, TSDB, scrape, native TLS/basic auth and API. It includes no
promtool, cloud discovery plugins or bundled Prometheus browser assets. OpsPilot's own real browser
flow uses its MCP/API, not the Prometheus UI. A scratch runtime contains only the non-root server,
module metadata and licenses; fixture config/PKI arrive via explicit mounts. No production/custom
customer Prometheus deployment is authorized. Build concurrency/heap are bounded for this host.

The final image must pass fresh raw scanning and the complete native F19 profile (including real
OIDC browser) again. [Checks](evidence/f19/checks.json) and final scan are authoritative; the
original failing image is retained as evidence. Nonblocking raw findings remain visible, and
these local gates never claim whole ASVS L2 or staging/live acceptance.
