"""Verify deployed observation worker has no business credentials or private key mounts."""

import json
import subprocess
from pathlib import Path

item = json.loads(subprocess.check_output(["docker", "inspect", "opspilot-full-ingress-worker-1"]))[
    0
]
assert item["State"]["Running"]
assert item["Config"]["User"] == "10001:10001"
assert item["HostConfig"]["ReadonlyRootfs"]
assert "ALL" in item["HostConfig"]["CapDrop"]
assert any(value.startswith("no-new-privileges") for value in item["HostConfig"]["SecurityOpt"])
assert 0 < item["HostConfig"]["Memory"] <= 256 * 1024 * 1024
binds = {mount["Destination"] for mount in item["Mounts"] if mount["Type"] in {"bind", "volume"}}
assert binds == {"/run/ingress.dsn"}
names = {line.split("=", 1)[0] for line in item["Config"]["Env"]}
assert not names.intersection(
    {
        "MCP_SERVICE_TOKEN",
        "DOMAIN_DATABASE_URL",
        "WORKFLOW_DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "CHECKPOINT_DATABASE_URL",
        "IDENTITY_DATABASE_URL",
        "SECRET_FILES",
        "SECRET_MANAGER_TOKEN_FILE",
        "CONNECTOR_MANAGER_TOKEN_FILE",
    }
)
assert item["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
result = {
    "passed": True,
    "running": True,
    "non_root": True,
    "read_only_rootfs": True,
    "caps_dropped": True,
    "no_new_privileges": True,
    "memory_bounded": True,
    "business_credentials": False,
    "manager_tokens": False,
    "private_key_mounts": False,
    "bind_destinations": sorted(binds),
    "automatic_restart": True,
    "image": item["Image"],
}
Path("docs/full/evidence/f18/worker-isolation.json").write_text(json.dumps(result, indent=2) + "\n")
print("Deployed ingress worker least-privilege environment/filesystem proof passed")
