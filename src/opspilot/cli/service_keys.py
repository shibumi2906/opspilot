"""Local key lifecycle. Private material is never printed or shipped to MCP."""

import argparse
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def grant_keys(path: Path) -> None:
    ring_file = path / "public" / "grants.json"
    if ring_file.exists():
        if not all(
            (path / "private" / (kid + ".pem")).exists() for kid in ("grant-current", "grant-next")
        ):
            raise ValueError("Incomplete grant key ring; refusing overwrite")
        return
    ring = {}
    for kid in ("grant-current", "grant-next"):
        key = Ed25519PrivateKey.generate()
        target = path / "private" / (kid + ".pem")
        if target.exists():
            raise ValueError("Refusing overwrite of grant private key")
        target.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        os.chmod(target, 0o600)
        ring[kid] = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        )
    ring_file.write_text(json.dumps(ring))


def initialize(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if (path / "public" / "keys.json").exists():
        if not all((path / "private" / (kid + ".pem")).exists() for kid in ("current", "next")):
            raise ValueError("Incomplete key ring; refusing overwrite")
        grant_keys(path)
        print("Existing independent Full service key ring preserved")
        return
    if any(path.iterdir()):
        raise ValueError("Refusing to overwrite existing key files")
    (path / "private").mkdir()
    (path / "public").mkdir()
    public = {}
    for kid in ("current", "next"):
        key = Ed25519PrivateKey.generate()
        target = path / "private" / (kid + ".pem")
        target.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        os.chmod(target, 0o600)
        public[kid] = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        )
    (path / "public" / "keys.json").write_text(json.dumps(public))
    grant_keys(path)
    print("Created independent service and grant rings; no private material printed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--retire", choices=["current", "next", "grant-current", "grant-next"])
    parser.add_argument(
        "--active", choices=["current", "next", "grant-current", "grant-next"], default="current"
    )
    parser.add_argument(
        "--grant-active", choices=["grant-current", "grant-next"], default="grant-current"
    )
    args = parser.parse_args()
    if args.retire:
        if args.retire == (args.grant_active if args.retire.startswith("grant-") else args.active):
            raise ValueError("Cannot retire the active signing key")
        file = (
            args.path
            / "public"
            / ("grants.json" if args.retire.startswith("grant-") else "keys.json")
        )
        ring = json.loads(file.read_text())
        ring.pop(args.retire, None)
        temp = file.with_suffix(".tmp")
        temp.write_text(json.dumps(ring))
        temp.replace(file)
        print("Retired verification key; tokens signed by it are now rejected")
    else:
        initialize(args.path)


if __name__ == "__main__":
    main()
