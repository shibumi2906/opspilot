"""Generate once, then preserve independent Full telemetry TLS/identity/seal material."""

import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _runtime_ownership(root: Path) -> None:
    # Root provisioning in Linux must match the non-root container UID.
    # The CA directory/key retain host ownership and are never mounted to runtime.
    if sys.platform != "win32" and os.geteuid() == 0:
        for role in ("collector", "api", "worker", "mcp", "probe"):
            directory = root / role
            os.chown(directory, 10001, 10001)
            directory.chmod(0o700)
            for path in directory.iterdir():
                if path.is_file():
                    os.chown(path, 10001, 10001)
                    path.chmod(0o600)


def prepare(root: Path) -> None:
    expected = [
        "collector/server.crt",
        "collector/server.key",
        "collector/receivers.json",
        "collector/integrity.key",
    ]
    expected += [
        f"{role}/{name}"
        for role in ("api", "worker", "mcp", "probe")
        for name in ("ca.crt", "client.crt", "client.key", "token")
    ]
    if root.exists():
        if not all((root / name).is_file() for name in expected):
            raise RuntimeError(
                "Partial telemetry credentials: preserve journal and recover original keys"
            )
        _runtime_ownership(root)
        return
    root.mkdir(parents=True, mode=0o700)
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "OpsPilot Full telemetry local CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(ca_key, hashes.SHA384())
    )

    def private(path: Path, key: rsa.RSAPrivateKey) -> None:
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        path.chmod(0o600)

    private(root / "ca.key", ca_key)
    (root / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    tokens = {}
    for role in ("collector", "api", "worker", "mcp", "probe"):
        directory = root / role
        directory.mkdir(mode=0o700)
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = "server" if role == "collector" else "client"
        private(directory / (name + ".key"), key)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "opspilot-" + role)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=60))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        ExtendedKeyUsageOID.SERVER_AUTH
                        if role == "collector"
                        else ExtendedKeyUsageOID.CLIENT_AUTH
                    ]
                ),
                False,
            )
        )
        if role == "collector":
            cert = cert.add_extension(
                x509.SubjectAlternativeName([x509.DNSName("collector"), x509.DNSName("localhost")]),
                False,
            )
        (directory / (name + ".crt")).write_bytes(
            cert.sign(ca_key, hashes.SHA384()).public_bytes(serialization.Encoding.PEM)
        )
        (directory / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        if role != "collector":
            token = secrets.token_hex(32)
            (directory / "token").write_text(token, encoding="ascii", newline="\n")
            (directory / "token").chmod(0o600)
            tokens[hashlib.sha256(token.encode()).hexdigest()] = "opspilot-" + role
    (root / "collector/receivers.json").write_text(json.dumps(tokens), encoding="utf-8")
    (root / "collector/integrity.key").write_text(secrets.token_hex(32), encoding="ascii")
    (root / "collector/integrity.key").chmod(0o600)
    _runtime_ownership(root)
