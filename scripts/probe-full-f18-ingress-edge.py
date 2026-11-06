"""Native TLS proxy routes signed ingress to the fail-closed API, never SPA fallback."""

import json
import ssl
from pathlib import Path
import httpx

context = ssl.create_default_context(cafile="/lab/ca.crt")
url = "https://app.opspilot.localhost:8443/ingress/v1/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/00000000-0000-4000-8000-000000000000"
with httpx.Client(verify=context, trust_env=False, timeout=5) as client:
    denied = client.post(url, content=b"{}", headers={"Content-Type": "application/json"})
    assert denied.status_code == 401 and denied.headers["content-type"].startswith(
        "application/json"
    )
    assert client.get(url).status_code == 403
    oversized = client.post(url, content=b"x" * 16385, headers={"Content-Type": "application/json"})
    assert oversized.status_code == 413
    assert "max-age=" in denied.headers["strict-transport-security"]
    assert "no-store" in denied.headers["cache-control"]
Path("/reports/f18-ingress-edge.json").write_text(
    json.dumps(
        {
            "passed": True,
            "native_tls": True,
            "unsigned_denied": 401,
            "get_denied": 403,
            "oversize_denied": 413,
            "hsts": True,
            "no_store": True,
        },
        indent=2,
    )
    + "\n"
)
print("F18 native TLS ingress edge routing/body/method/security headers passed")
