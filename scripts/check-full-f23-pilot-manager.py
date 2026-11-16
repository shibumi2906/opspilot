"""Actual recovered-pilot manager rotation/revoke/seal/config-rollback checks."""

import argparse
import json
import re
import secrets
import ssl
import subprocess
import time
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from opspilot.security.keys import version
from opspilot.security.manager import BaoGrantKeys, ManagerUnavailable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", args.project)
    private = Path(".tools") / args.project
    state = json.loads((private / "manager-recovery/initialization.json").read_bytes())
    root = state["root_token"]
    manager = private / "manager"
    writer = BaoGrantKeys(
        "https://127.0.0.1:18270", str(manager / "ca.crt"), str(manager / "worker.token")
    )
    reader = BaoGrantKeys(writer.origin, writer.ca_file, str(manager / "mcp.token"))
    checks = []
    with httpx.Client(
        base_url=writer.origin,
        trust_env=False,
        timeout=5,
        verify=ssl.create_default_context(cafile=writer.ca_file),
    ) as client:

        def call(method, path, body=None):
            response = client.request(
                method, "/v1/" + path, json=body, headers={"X-Vault-Token": root}
            )
            if response.status_code not in {200, 204}:
                raise RuntimeError("Pilot manager request denied; private response withheld")
            return response.json() if response.content else {}

        def read(name):
            return call("GET", "core/data/grants/" + name)["data"]["data"]

        def update(name, value):
            record = call("GET", "core/data/grants/" + name)["data"]
            return call(
                "POST",
                "core/data/grants/" + name,
                {"options": {"cas": record["metadata"]["version"]}, "data": value},
            )

        active, public = read("active"), read("public")
        reference, raw = writer.signing_key("grant-current")
        now = int(time.time())
        token = jwt.encode(
            {"sub": "pilot-rotation", "iat": now, "exp": now + 120},
            raw,
            algorithm="EdDSA",
            headers={"kid": reference.kid},
        )
        jwt.decode(token, reader.verification_key(reference.kid), algorithms=["EdDSA"])
        checks.append("TLS worker signing and MCP public verification")
        try:
            reader.signing_key("grant-current")
        except ManagerUnavailable:
            checks.append("MCP private-key access denied")
        else:
            raise AssertionError("MCP signing material exposed")
        try:
            replacement = Ed25519PrivateKey.generate()
            kid = version("grant-current", replacement.public_key())
            revision = secrets.randbelow(900000000) + 3
            call(
                "POST",
                f"core/data/grants/private/{revision}",
                {
                    "options": {"cas": 0},
                    "data": {
                        "pem": replacement.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        ).decode()
                    },
                },
            )
            overlap = {
                **public,
                kid: replacement.public_key()
                .public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
                )
                .decode(),
            }
            update("public", overlap)
            update("active", {**active, "grant-current": revision})
            assert writer.signing_key("grant-current")[0].kid == kid
            jwt.decode(token, reader.verification_key(reference.kid), algorithms=["EdDSA"])
            checks.append("new signing version and old signature overlap")
            overlap.pop(reference.kid)
            update("public", overlap)
            try:
                reader.verification_key(reference.kid)
            except ManagerUnavailable:
                checks.append("revoked signing identity denied")
            else:
                raise AssertionError("Revoked key accepted")
            victim = call(
                "POST",
                "auth/token/create",
                {"policies": ["f17-worker"], "no_default_policy": True, "ttl": "60s"},
            )["auth"]["client_token"]
            headers = {"X-Vault-Token": victim}
            assert client.get("/v1/core/data/grants/public", headers=headers).status_code == 200
            call("POST", "auth/token/revoke", {"token": victim})
            assert client.get("/v1/core/data/grants/public", headers=headers).status_code == 403
            checks.append("revoked service token denied")
            call("PUT", "sys/seal")
            try:
                writer.signing_key("grant-current")
            except ManagerUnavailable:
                checks.append("sealed manager fails closed without file fallback")
            else:
                raise AssertionError("Sealed manager fell back to file key")
        finally:
            if call("GET", "sys/seal-status")["sealed"]:
                for share in state["keys"][:2]:
                    call("PUT", "sys/unseal", {"key": share})
            for _ in range(30):
                if client.get("/v1/sys/health").status_code == 200:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Manager unavailable after unseal")
            update("public", public)
            update("active", active)
        assert writer.signing_key("grant-current")[0] == reference
        checks.append("original identity restored through safe CAS configuration rollback")
        audit = subprocess.check_output(
            ["docker", "exec", args.project + "-manager-manager-1", "cat", "/bao/audit/audit.json"],
            timeout=30,
        )
        assert raw not in audit and root.encode() not in audit
        checks.append("protected audit contains no raw private key or root credential")
    report = Path("docs/full/evidence/f23/local-pilot-20261116") / (
        "manager-rotation-" + args.project + ".json"
    )
    with report.open("x") as handle:
        json.dump(
            {
                "passed": True,
                "project": args.project,
                "checks": checks,
                "scope": (
                    "actual recovered pilot manager; signature overlap, "
                    "not an in-flight business-job claim"
                ),
                "deployment_image_rollback": "NOT_RUN",
            },
            handle,
            indent=2,
        )
    print(json.dumps({"passed": True, "manager_checks": len(checks)}))


if __name__ == "__main__":
    main()
