"""Public package/image inventory. Never dump Docker environment or secret mounts."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def command(args):
    return subprocess.check_output(args, text=True).strip()


images = []
for name in (
    "opspilot-full/app:f01",
    "opspilot-full/web:f01",
    "opspilot-full/redis:f15",
    "opspilot-full/oidc:f03",
    "opspilot-full/postgres:f01",
    "opspilot-full/manager:f17",
):
    item = json.loads(command(["docker", "image", "inspect", name]))[0]
    images.append(
        {
            "reference": name,
            "id": item["Id"],
            "repo_digests": item.get("RepoDigests"),
            "created": item["Created"],
            "os": item["Os"],
            "architecture": item["Architecture"],
        }
    )
python_packages = json.loads(
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            "opspilot-full/app:f01",
            "-c",
            "import importlib.metadata as m,json; print(json.dumps(sorted([{'name':d.metadata['Name'],'version':d.version} for d in m.distributions()],key=lambda x:x['name'])))",
        ]
    )
)
lock = json.loads(Path("web/package-lock.json").read_text())
node_packages = [
    {"path": name, "version": value.get("version")}
    for name, value in lock["packages"].items()
    if name
]
hashes = {
    name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
    for name in (
        "uv.lock",
        "web/package-lock.json",
        "Dockerfile",
        "infra/full/Dockerfile",
        "web/Dockerfile",
        "infra/identity/Dockerfile",
        "infra/identity/OpsIdentityProbe.java",
        "compose.full.yaml",
        "compose.full.f17-local.yaml",
        "compose.full.f17-checks.yaml",
        "infra/secrets-manager/Dockerfile",
        "infra/secrets-manager/patch_jose3.py",
        "infra/secrets-manager/regression_test.go",
        "docs/full/f17-crypto-inventory.json",
        "docs/full/f18-crypto-inventory.json",
        "compose.full.f18-checks.yaml",
        "compose.full.f18-local.yaml",
        "web/nginx.conf",
        "infra/security/nginx.conf",
        "migrations/versions/0019_adapters.py",
    )
}
result = {
    "observed_at_utc": datetime.now(UTC).isoformat(),
    "source_base": "017b68bb34e85e95013076d570bd14b5519f842b",
    "source_dirty": bool(command(["git", "status", "--porcelain"])),
    "images": images,
    "python_packages": python_packages,
    "node_lock_packages": node_packages,
    "artifact_hashes": hashes,
    "patch_policy": "../../f18-security-contracts.md",
    "secrets_in_inventory": False,
    "manager_vendor_patch_proof": "../f17/security/manager-patch-proof.json",
    "inherited_patch_proof_policy": "Exact unchanged image ID required; fresh F18 vulnerability scans recorded separately",
    "whole_L2": "NOT_MET",
}
Path("docs/full/evidence/f18/inventory.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "images": len(images),
            "python_packages": len(python_packages),
            "node_packages": len(node_packages),
        }
    )
)
