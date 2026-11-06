"""Real manager ACL, overlap/retirement and revoked-token drill; operator root stays on host."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
spec = importlib.util.spec_from_file_location("f18setup", ROOT / "scripts/setup-full-f18.py")
f18 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f18)
m = f18.manager()
fixture = json.loads((f18.PRIVATE / "fixture.json").read_text())
os.environ["F18_TEST_INGRESS_PASSWORD"] = fixture["db_password"]
os.environ["F18_SUBNET_PREFIX"] = "10.245.21"
compose = ["docker", "compose", "--env-file", ".env", "-p", "opspilot-full-test-f18-r4"]
for file in (
    "compose.full.yaml",
    "compose.full.test.yaml",
    "compose.full.f13-checks.yaml",
    "compose.full.f16-checks.yaml",
    "compose.full.f17-checks.yaml",
    "compose.full.f18-checks.yaml",
):
    compose += ["-f", file]
report = ROOT / "docs/full/evidence/f18/manager"
report.mkdir(parents=True, exist_ok=True)


def probe(phase, revoked=False):
    args = compose + [
        "run",
        "--rm",
        "--no-deps",
        "-v",
        str(ROOT / "scripts/probe-full-f18-rotation.py") + ":/app/f18_rotation.py:ro",
        "-v",
        str(report) + ":/reports",
        "-e",
        "F18_ROTATION_PHASE=" + phase,
    ]
    if revoked:
        args += [
            "-v",
            str(f18.CLIENT / "revoked.token") + ":/run/revoked/token:ro",
            "-e",
            "CONNECTOR_MANAGER_TOKEN_FILE=/run/revoked/token",
        ]
    result = subprocess.run(
        args + ["tests", "python", "/app/f18_rotation.py"], capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError("F18 rotation probe failed: " + phase + "; inspect local log")
    print(phase, "passed")


root = json.loads((m.RECOVERY / "initialization.json").read_text())["root_token"]
case = fixture["cases"][0]
prefix = "core/data/connectors/" + case["tenant_id"] + "/" + case["connector_id"]
acl = []
with m.client() as client:
    for role, path, expected in [
        ("mcp", prefix + "/credential", 200),
        ("mcp", prefix + "/webhook", 403),
        ("ingress", prefix + "/webhook", 200),
        ("ingress", prefix + "/credential", 403),
        ("mcp", "core/data/grants/private/1", 403),
        ("ingress", "core/data/grants/private/1", 403),
        (
            "mcp",
            "core/data/connectors/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/00000000-0000-4000-8000-000000000000/credential",
            403,
        ),
        (
            "ingress",
            "core/data/connectors/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/00000000-0000-4000-8000-000000000000/webhook",
            403,
        ),
        (
            "tenant-a",
            "core/data/connectors/"
            + fixture["cases"][1]["tenant_id"]
            + "/"
            + fixture["cases"][1]["connector_id"]
            + "/webhook",
            403,
        ),
    ]:
        response = client.get(
            "/v1/" + path,
            headers={"X-Vault-Token": (f18.CLIENT / (role + ".token")).read_text().strip()},
        )
        assert response.status_code == expected
        acl.append(
            {
                "role": role,
                "purpose": path.rsplit("/", 1)[1],
                "expected_status": expected,
                "passed": True,
            }
        )
    original = m.call(client, "GET", prefix + "/webhook", token=root)["data"]["data"]

    def replace(data):
        current = m.call(client, "GET", prefix + "/webhook", token=root)["data"]
        m.call(
            client,
            "POST",
            prefix + "/webhook",
            {"options": {"cas": current["metadata"]["version"]}, "data": data},
            root,
        )

    try:
        probe("overlap")
        replace({**original, "keys": {"h2": original["keys"]["h2"]}})
        probe("retired")
    finally:
        replace(original)
    probe("restored")
    token = m.call(
        client,
        "POST",
        "auth/token/create",
        {"policies": ["f18-ingress"], "no_default_policy": True, "ttl": "5m", "renewable": False},
        root,
    )["auth"]["client_token"]
    (f18.CLIENT / "revoked.token").write_text(token)
    m.call(client, "POST", "auth/token/revoke", {"token": token}, root)
    probe("revoked", True)
result = {
    "passed": True,
    "acl": acl,
    "overlap": True,
    "retired_h1_denied_h2_accepted": True,
    "accepted_h1_jobs_processed_after_retirement": True,
    "original_ring_restored": True,
    "revoked_service_token_fail_closed": True,
    "operator_secrets_in_apps": False,
}
(report / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
print("F18 manager ACL/key rotation/revoke drill passed; credentials withheld")
