"""Unseal the existing F20 manager and replace expired tokens, preserving keys and ACLs.

No bootstrap, connector enrollment, database mutation or Jira request is performed.
"""

import argparse
import json
import re
import ssl
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"opspilot-full-test-f20-[a-z0-9]+", args.project):
        raise SystemExit("Existing isolated F20 project required")
    private = Path(".tools/f20") / args.project
    manager = private / "manager"
    config = json.loads((manager / "compose.json").read_bytes())
    if config["name"] != args.project + "-manager":
        raise SystemExit("Manager project mismatch")
    # Derive the loopback port from the existing trusted local configuration.
    binding = config["services"]["manager"]["ports"][0]
    if not re.fullmatch(r"127\.0\.0\.1:[0-9]+:8200", binding):
        raise SystemExit("Loopback manager binding required")
    port = int(binding.split(":")[1])
    state = json.loads((private / "recovery/initialization.json").read_bytes())
    with httpx.Client(
        base_url=f"https://127.0.0.1:{port}",
        verify=ssl.create_default_context(cafile=str(manager / "ca.crt")),
        trust_env=False,
        timeout=10,
    ) as client:
        def call(method, path, body=None):
            response = client.request(
                method,
                "/v1/" + path,
                json=body,
                headers={"X-Vault-Token": state["root_token"]},
            )
            if response.status_code != 200:
                raise SystemExit(
                    f"Manager refresh denied ({method} {path}, HTTP {response.status_code}); "
                    "private response withheld"
                )
            return response.json()

        if call("GET", "sys/seal-status")["sealed"]:
            for share in state["keys"][:2]:
                call("PUT", "sys/unseal", {"key": share})
        for _ in range(30):
            if client.get("/v1/sys/health").status_code == 200:
                break
            time.sleep(1)
        else:
            raise SystemExit("Manager leader did not become ready after unseal")
        for role in ("worker", "mcp"):
            policy = "f17-" + role
            before = call("GET", "sys/policies/acl/" + policy)["data"]["policy"]
            token = call(
                "POST",
                "auth/token/create",
                {
                    "policies": [policy],
                    "no_default_policy": True,
                    "ttl": "1h",
                    "explicit_max_ttl": "1h",
                    "renewable": False,
                    "display_name": "f20-" + role,
                },
            )
            (manager / (role + ".token")).write_text(token["auth"]["client_token"])
            assert call("GET", "sys/policies/acl/" + policy)["data"]["policy"] == before
    print("F20 tokens refreshed; existing ACLs and signing keys preserved; no Jira calls")


if __name__ == "__main__":
    main()
