"""Check actual local credential values against bounded runtime logs; values never exported."""

import json
import re
import runpy
import subprocess
from pathlib import Path

state = runpy.run_path("scripts/check-full-f18-secrets.py")
values = state["values"]
containers = [
    "opspilot-full-api-1",
    "opspilot-full-mcp-1",
    "opspilot-full-worker-1",
    "opspilot-full-worker2-1",
    "opspilot-full-ingress-worker-1",
    "opspilot-full-web-1",
    "opspilot-full-collector-1",
    "opspilot-full-manager-1",
    "opspilot-full-test-f18-r4-api-1",
    "opspilot-full-test-f18-r4-mcp-1",
    "opspilot-full-test-f18-r4-adapter-simulator-1",
    "opspilot-full-test-f18-tls-api-1",
    "opspilot-full-test-f18-tls-mcp-1",
    "opspilot-full-test-f18-tls-worker-1",
    "opspilot-full-test-f18-tls-web-1",
    "opspilot-full-test-f18-tls-collector-1",
    "opspilot-full-test-f18-regression-browser-api-1",
    "opspilot-full-test-f18-regression-browser-mcp-1",
    "opspilot-full-test-f18-regression-browser-worker-1",
    "opspilot-full-test-f18-regression-browser-web-1",
    "opspilot-full-test-f17-manager-r2-manager-1",
]
for name in containers:
    result = subprocess.run(
        ["docker", "logs", name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, "Runtime log unavailable: " + name
    content = result.stdout + result.stderr
    assert not any(secret in content for secret in values), "Credential match in runtime: " + name
    assert not re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content), (
        "Private key material in runtime: " + name
    )
    assert "F18_SENTINEL" not in content, "Producer sentinel in runtime: " + name
report = {
    "passed": True,
    "containers_checked": containers,
    "credential_matches": 0,
    "private_key_matches": 0,
    "producer_sentinel_matches": 0,
    "values_exported": False,
}
Path("docs/full/evidence/f18/runtime-secret-check.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print("F18 current credential and sentinel runtime log gate passed; values withheld")
