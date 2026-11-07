"""Enroll only the approved staging read credential in the isolated test manager."""

import importlib.util
import json
import shutil
from pathlib import Path
from uuid import UUID, uuid5

ROOT = Path.cwd()
CLIENT = ROOT / ".tools/f19-aws-staging/client"
spec = importlib.util.spec_from_file_location("f17", ROOT / "scripts/setup-full-f17-manager.py")
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
manager.bootstrap()
rows = json.loads((CLIENT / "registry.json").read_text())
reg = rows[0]
reg["connector_id"] = str(uuid5(UUID(reg["tenant_id"]), "f19-aws-staging-v1"))
(CLIENT / "registry.json").write_text(json.dumps(rows))
shutil.copyfile(manager.PRIVATE / "ca.crt", CLIENT / "manager-ca.crt")
credential = json.loads((ROOT / ".tools/f19-aws-staging/credential.json").read_text())
root = json.loads((manager.RECOVERY / "initialization.json").read_text())["root_token"]
path = f"core/data/connectors/{reg['tenant_id']}/{reg['connector_id']}/credential"
with manager.client() as client:
    previous = client.get("/v1/" + path, headers={"X-Vault-Token": root})
    if previous.status_code == 404:
        manager.call(
            client,
            "POST",
            path,
            {
                "options": {"cas": 0},
                "data": {
                    "tenant_id": reg["tenant_id"],
                    "connector_id": reg["connector_id"],
                    **credential,
                },
            },
            root,
        )
    elif previous.status_code != 200 or previous.json()["data"]["data"] != {
        "tenant_id": reg["tenant_id"],
        "connector_id": reg["connector_id"],
        **credential,
    }:
        raise RuntimeError("Existing staging credential mismatch; do not overwrite")
    manager.call(
        client,
        "PUT",
        "sys/policies/acl/f19-aws-mcp",
        {"policy": f'path "{path}" {{ capabilities=["read"] }}'},
        root,
    )
    token = manager.call(
        client,
        "POST",
        "auth/token/create",
        {
            "policies": ["f19-aws-mcp"],
            "no_default_policy": True,
            "ttl": "1h",
            "explicit_max_ttl": "1h",
            "renewable": False,
            "display_name": "f19-aws-mcp",
        },
        root,
    )
    (CLIENT / "mcp.token").write_text(token["auth"]["client_token"])
print("AWS staging credential enrolled; exact read-only test-manager ACL; values withheld")
