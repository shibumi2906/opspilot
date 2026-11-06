"""Prepare isolated F18 test PKI/fixtures and narrow real OpenBao service policies.

Preserve existing credentials and manager state. Never print secrets or mount operator
root/unseal/CA-key material into applications. Run after the MVP prerequisite gate.
"""

import importlib.util
import argparse
import ipaddress
import json
import secrets
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path.cwd()))
from tests.f18_cases import CASES

ROOT = Path.cwd()
PRIVATE = ROOT / ".tools/f18-private"
SERVER = ROOT / ".tools/f18-simulator"
PROBE = ROOT / ".tools/f18-probe"
CLIENT = ROOT / ".tools/f18-client"
LOCAL = False


def manager():
    spec = importlib.util.spec_from_file_location(
        "f17_manager", ROOT / "scripts/setup-full-f17-manager.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if LOCAL:
        module.local_profile()
    return module


def prepare() -> None:
    for folder in (PRIVATE, SERVER, PROBE, CLIENT):
        folder.mkdir(parents=True, exist_ok=True)
    fixture = PRIVATE / "fixture.json"
    if not fixture.exists():
        value = {
            "db_password": secrets.token_hex(32),
            "control_token": secrets.token_hex(32),
            "cases": [
                {
                    **case,
                    "credential": secrets.token_hex(32),
                    "keys": {"h1": secrets.token_hex(32), "h2": secrets.token_hex(32)},
                }
                for case in CASES
            ],
        }
        fixture.write_text(json.dumps(value))
    value = json.loads(fixture.read_text())
    database = "opspilot_full" if LOCAL else "opspilot_full_test"
    (CLIENT / "ingress.dsn").write_text(
        f"postgresql+psycopg://ops_ingress:{value['db_password']}@postgres/{database}"
    )
    (PROBE / "fixture.json").write_text(json.dumps(value))
    (SERVER / "credentials.json").write_text(
        json.dumps(
            {
                "control_token": value["control_token"],
                "cases": [
                    {k: v for k, v in case.items() if k != "keys"} for case in value["cases"]
                ],
            }
        )
    )
    if not (CLIENT / "simulator-ca.crt").exists():
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F18 isolated simulator CA")])
        now = datetime.now(UTC)
        ca = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .sign(ca_key, hashes.SHA384())
        )
        (PRIVATE / "ca.key").write_bytes(
            ca_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        for folder in (CLIENT, PROBE):
            (folder / "simulator-ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        for prefix, folder, hosts in (
            ("server", SERVER, ["adapter-simulator"]),
            ("api", PROBE, ["localhost"]),
        ):
            key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            sans = [x509.DNSName(h) for h in hosts] + [
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
            ]
            cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=15))
                .add_extension(x509.SubjectAlternativeName(sans), False)
                .sign(ca_key, hashes.SHA384())
            )
            (folder / (prefix + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (folder / (prefix + ".key")).write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
    m = manager()
    m.bootstrap()
    shutil.copyfile(m.PRIVATE / "ca.crt", CLIENT / "manager-ca.crt")
    state = json.loads((m.RECOVERY / "initialization.json").read_text())
    with m.client() as c:
        root = state["root_token"]
        for case in value["cases"]:
            prefix = f"connectors/{case['tenant_id']}/{case['connector_id']}"
            for purpose, body in (
                ("credential", {"token": case["credential"]}),
                ("webhook", {"keys": case["keys"]}),
            ):
                path = "core/data/" + prefix + "/" + purpose
                exists = c.get("/v1/" + path, headers={"X-Vault-Token": root})
                if exists.status_code == 404:
                    m.call(
                        c,
                        "POST",
                        path,
                        {
                            "options": {"cas": 0},
                            "data": {
                                "tenant_id": case["tenant_id"],
                                "connector_id": case["connector_id"],
                                **body,
                            },
                        },
                        root,
                    )
                elif exists.status_code != 200:
                    raise RuntimeError("Existing connector manager state unavailable")
        policies = {
            role: "\n".join(
                f'path "core/data/connectors/{case["tenant_id"]}/{case["connector_id"]}/{purpose}" '
                '{ capabilities=["read"] }'
                for case in value["cases"]
            )
            for role, purpose in (("mcp", "credential"), ("ingress", "webhook"))
        }
        policies.update(
            {
                "tenant-a": f'path "core/data/connectors/{CASES[0]["tenant_id"]}/*" {{ capabilities=["read"] }}',
            }
        )
        for role, policy in policies.items():
            m.call(c, "PUT", "sys/policies/acl/f18-" + role, {"policy": policy}, root)
            token = m.call(
                c,
                "POST",
                "auth/token/create",
                {
                    "policies": ["f18-" + role],
                    "no_default_policy": True,
                    "ttl": "1h",
                    "explicit_max_ttl": "1h",
                    "renewable": False,
                    "display_name": "f18-" + role,
                },
                root,
            )
            (CLIENT / (role + ".token")).write_text(token["auth"]["client_token"])
    print(
        "F18 independent DB credential, simulator TLS and real per-service connector ACLs ready; values withheld"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    LOCAL = parser.parse_args().local
    if LOCAL:
        PRIVATE = ROOT / ".tools/f18-private-dev"
        SERVER = ROOT / ".tools/f18-simulator-dev"
        PROBE = ROOT / ".tools/f18-probe-dev"
        CLIENT = ROOT / ".tools/f18-client-dev"
    prepare()
