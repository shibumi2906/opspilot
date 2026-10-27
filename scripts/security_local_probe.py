"""Read-only TLS and security policy probes against the generated lab."""

import json
import ssl
import time
from pathlib import Path

import httpx
import psycopg
from sqlalchemy.engine import make_url

ca = ssl.create_default_context(cafile="/lab/ca.crt")
checks = []
deadline = time.monotonic() + 90
while True:
    try:
        metadata = httpx.get(
            "https://idp.opspilot.localhost:8543/realms/opspilot/.well-known/openid-configuration",
            verify=ca,
            timeout=3,
        )
        metadata.raise_for_status()
        assert metadata.json()["issuer"] == "https://idp.opspilot.localhost:8543/realms/opspilot"
        break
    except httpx.HTTPError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
checks.append("IdP discovery is ready on the pinned trusted TLS issuer")
import base64

keys = httpx.get(metadata.json()["jwks_uri"], verify=ca).json()["keys"]
assert all(
    int.from_bytes(base64.urlsafe_b64decode(k["n"] + "=="), "big").bit_length() >= 3072
    for k in keys
    if k.get("alg") == "RS256"
)
assert any(k.get("alg") == "RS256" for k in keys)
checks.append("Effective provider RS256 signing keys are at least RSA 3072")
for path, status in [("/", 200), ("/auth/me", 401), ("/api/v2/runs", 401)]:
    r = httpx.get("https://app.opspilot.localhost:8443" + path, verify=ca)
    assert r.status_code == status
    for name in [
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
    ]:
        assert name in r.headers
    assert r.headers["cache-control"] == "no-store"
    assert "includeSubDomains" in r.headers["strict-transport-security"]
checks.append("TLS UI/API policy present on public success and authentication denial")
for url, context in [("https://app.opspilot.localhost:8443", True), ("https://web:8443", ca)]:
    try:
        httpx.get(url, verify=context)
        raise AssertionError("Untrusted or mismatched certificate accepted")
    except httpx.ConnectError as exc:
        assert "CERTIFICATE_VERIFY_FAILED" in str(exc)
checks.append("Untrusted CA and wrong TLS hostname rejected without bypass")
for target in ["api:8000/health", "mcp:8001/mcp", "oidc:8543/realms/opspilot"]:
    try:
        r = httpx.get("http://" + target, timeout=3)
        assert r.status_code >= 400
    except (httpx.RemoteProtocolError, httpx.ReadError):
        pass
checks.append("API MCP and IdP do not serve plaintext HTTP")
r = httpx.post("https://mcp:8001/mcp", verify=ca, json={})
assert r.status_code == 401
checks.append("MCP requires signed request context over TLS")
raw = make_url(Path("/lab/identity.dsn").read_text())
kwargs = dict(host="postgres", dbname=raw.database, user=raw.username, password=raw.password)
with psycopg.connect(**kwargs, sslmode="verify-full", sslrootcert="/lab/ca.crt") as conn:
    version = conn.execute("SELECT version FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[
        0
    ]
    assert version in ["TLSv1.2", "TLSv1.3"]
    try:
        conn.execute("DELETE FROM identity.security_events WHERE false")
        raise AssertionError("Identity runtime can delete audit events")
    except psycopg.errors.InsufficientPrivilege:
        conn.rollback()
checks.append("Database verifies TLS peer; application role cannot delete security audit")
try:
    psycopg.connect(**kwargs, sslmode="disable")
    raise AssertionError("Database accepted plaintext authentication")
except psycopg.OperationalError:
    pass
checks.append("PostgreSQL rejects non-TLS network authentication")
result = {"passed": True, "checks": checks, "database_tls": version}
Path("/reports/tls-probes.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
