"""Local-only Prometheus TLS/basic auth + exact manager ACL; no staging enrollment.

Run using uv run --frozen --with bcrypt==5.0.0 python scripts/setup-full-f19.py.
Private files are ignored and never printed; preserve existing credentials/PKI.
"""

import importlib.util
import json
import os
import secrets
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path.cwd()))
from tests.f19_cases import CASES

ROOT = Path.cwd()
PRIVATE = ROOT / ".tools/f19-private"
SERVER = ROOT / ".tools/f19-server"
CLIENT = ROOT / ".tools/f19-client"
PROBE = ROOT / ".tools/f19-probe"


def prepare():
    for folder in (PRIVATE, SERVER, CLIENT, PROBE):
        folder.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / "fixture-v1.json"
    if not path.exists():
        path.write_text(
            json.dumps(
                {
                    "control": secrets.token_hex(32),
                    "credentials": [
                        {"username": f"opspilot_{index}", "password": secrets.token_hex(32)}
                        for index in range(len(CASES))
                    ],
                }
            )
        )
    private = json.loads(path.read_text())
    (PROBE / "fixture.json").write_text(json.dumps(private))
    if not (PROBE / "invalid.token").exists():
        (PROBE / "invalid.token").write_text("hvs." + secrets.token_hex(32))
    (SERVER / "control").write_text(private["control"])
    if not (SERVER / "server.crt").exists():
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F19 local fixture CA")])
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
        (CLIENT / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cert = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F19 metric fixture")])
            )
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=15))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("prometheus"), x509.DNSName("metric-fixture")]
                ),
                False,
            )
            .sign(ca_key, hashes.SHA384())
        )
        (SERVER / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (SERVER / "server.key").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    # Repair the draft leaf's ambiguous CA-equal subject without rotating either key/CA.
    leaf = x509.load_pem_x509_certificate((SERVER / "server.crt").read_bytes())
    issuer = x509.load_pem_x509_certificate((CLIENT / "ca.crt").read_bytes())
    if leaf.subject == issuer.subject:
        signing_key = serialization.load_pem_private_key((PRIVATE / "ca.key").read_bytes(), None)
        repaired = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F19 metric fixture")])
            )
            .issuer_name(issuer.subject)
            .public_key(leaf.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(leaf.not_valid_before_utc)
            .not_valid_after(leaf.not_valid_after_utc)
            .add_extension(
                leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value, False
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .sign(signing_key, hashes.SHA384())
        )
        (SERVER / "server.crt").write_bytes(repaired.public_bytes(serialization.Encoding.PEM))
    web = SERVER / "web-v1.json"
    if not web.exists():
        web.write_text(
            json.dumps(
                {
                    "tls_server_config": {
                        "cert_file": "/run/fixture/server.crt",
                        "key_file": "/run/fixture/server.key",
                        "min_version": "TLS12",
                    },
                    "basic_auth_users": {
                        item["username"]: bcrypt.hashpw(
                            item["password"].encode(), bcrypt.gensalt()
                        ).decode()
                        for item in private["credentials"]
                    },
                }
            )
        )
    (SERVER / "prometheus.json").write_text(
        json.dumps(
            {
                "global": {"scrape_interval": "1s", "scrape_timeout": "500ms"},
                "scrape_configs": [
                    {
                        "job_name": "opspilot",
                        "sample_limit": 100,
                        "static_configs": [{"targets": ["metric-fixture:8080"]}],
                    }
                ],
            }
        )
    )
    registrations = [
        {
            **case,
            "origin": "https://prometheus:8443",
            "addresses": [os.environ.get("F19_SUBNET_PREFIX", "10.245.25") + ".10"],
            "ca_file": "/run/prometheus-client/ca.crt",
            "targets": ["primary", "replica"],
            "deployment": "fixture",
            "dataset": "synthetic",
            "allow_private": True,
            "authorization_ref": "user-approved local F19 fixture only",
        }
        for case in CASES
    ]
    (CLIENT / "registry.json").write_text(json.dumps(registrations))
    spec = importlib.util.spec_from_file_location(
        "f17_manager", ROOT / "scripts/setup-full-f17-manager.py"
    )
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    manager.bootstrap()
    shutil.copyfile(manager.PRIVATE / "ca.crt", CLIENT / "manager-ca.crt")
    root = json.loads((manager.RECOVERY / "initialization.json").read_text())["root_token"]
    with manager.client() as c:
        for index, case in enumerate(CASES):
            path = f"core/data/connectors/{case['tenant_id']}/{case['connector_id']}/credential"
            response = c.get("/v1/" + path, headers={"X-Vault-Token": root})
            if response.status_code == 404:
                manager.call(
                    c,
                    "POST",
                    path,
                    {
                        "options": {"cas": 0},
                        "data": {
                            "tenant_id": case["tenant_id"],
                            "connector_id": case["connector_id"],
                            **private["credentials"][index],
                        },
                    },
                    root,
                )
            elif response.status_code != 200:
                raise RuntimeError("F19 manager existing credential unavailable")
        policy = "\n".join(
            f'path "core/data/connectors/{case["tenant_id"]}/{case["connector_id"]}/credential" '
            '{ capabilities=["read"] }'
            for case in CASES
        )
        manager.call(c, "PUT", "sys/policies/acl/f19-mcp", {"policy": policy}, root)
        token = manager.call(
            c,
            "POST",
            "auth/token/create",
            {
                "policies": ["f19-mcp"],
                "no_default_policy": True,
                "ttl": "1h",
                "explicit_max_ttl": "1h",
                "renewable": False,
                "display_name": "f19-mcp",
            },
            root,
        )
        (CLIENT / "mcp.token").write_text(token["auth"]["client_token"])
    print("F19 local TLS/basic auth and exact credential ACL ready; values withheld")


if __name__ == "__main__":
    prepare()
