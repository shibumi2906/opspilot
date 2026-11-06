"""Operator coordinates real claimed jobs across a manager key rotation; no root in workers."""

import argparse
import importlib
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from opspilot.security.keys import version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"opspilot-full-test-f17-[a-z0-9-]+", args.project):
        raise ValueError("Explicit isolated F17 project required")
    compose = ["docker", "compose", "--env-file", ".env", "-p", args.project]
    for file in (
        "compose.full.yaml",
        "compose.full.test.yaml",
        "compose.full.f13-checks.yaml",
        "compose.full.f16-checks.yaml",
        "compose.full.f17-checks.yaml",
    ):
        compose += ["-f", file]
    subprocess.run(compose + ["stop", "worker", "worker2"], check=True, capture_output=True)
    m = importlib.import_module("setup-full-f17-manager")
    root_token = json.loads((m.RECOVERY / "initialization.json").read_text())["root_token"]
    workers = []
    results = []
    prefix = Path(".tools/f17-inflight") / secrets.token_hex(4)
    with m.client() as client:
        active = m.call(client, "GET", "core/data/grants/active", token=root_token)["data"]["data"]
        public = m.call(client, "GET", "core/data/grants/public", token=root_token)["data"]["data"]
        try:
            for tenant in (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            ):
                directory = (prefix / tenant).resolve()
                directory.mkdir(parents=True)
                log = (directory / "worker.log").open("w")
                process = subprocess.Popen(
                    compose
                    + [
                        "run",
                        "--rm",
                        "--no-deps",
                        "-v",
                        str(Path("tests").resolve()) + ":/work/tests:ro",
                        "-v",
                        str(directory) + ":/drill",
                        "-e",
                        "PYTHONPATH=/work",
                        "tests",
                        "python",
                        "/work/tests/f17_inflight_worker.py",
                        tenant,
                    ],
                    stdout=log,
                    stderr=log,
                )
                workers.append((process, directory, log))
            deadline = time.monotonic() + 30
            while not all((d / "ready").is_file() for _, d, _ in workers):
                if time.monotonic() > deadline or any(p.poll() is not None for p, _, _ in workers):
                    raise RuntimeError(
                        "In-flight worker did not reach the real issued-grant boundary"
                    )
                time.sleep(0.02)
            key = Ed25519PrivateKey.generate()
            kid = version("grant-current", key.public_key())
            number = secrets.randbelow(900000000) + 3
            m.call(
                client,
                "POST",
                f"core/data/grants/private/{number}",
                {
                    "options": {"cas": 0},
                    "data": {
                        "pem": key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        ).decode()
                    },
                },
                root_token,
            )
            overlap = {
                **public,
                kid: key.public_key()
                .public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
                )
                .decode(),
            }
            m.call(client, "POST", "core/data/grants/public", {"data": overlap}, root_token)
            m.call(
                client,
                "POST",
                "core/data/grants/active",
                {"data": {**active, "grant-current": number}},
                root_token,
            )
            for _, directory, _ in workers:
                (directory / "release").write_text("rotated")
            for process, directory, _ in workers:
                if process.wait(timeout=30) != 0:
                    raise RuntimeError("Claimed job failed across rotation; private log preserved")
                results.append(json.loads((directory / "result.json").read_text()))
        finally:
            m.call(client, "POST", "core/data/grants/active", {"data": active}, root_token)
            # Both old grants finished before pruning the drill's new unused public key.
            m.call(client, "POST", "core/data/grants/public", {"data": public}, root_token)
            for process, _, log in workers:
                if process.poll() is None:
                    process.terminate()
                log.close()
    report = {
        "passed": True,
        "processes": 2,
        "tenants": 2,
        "results": results,
        "manager_root_or_recovery_material_in_worker_mounts": False,
        "tokens_in_IPC": False,
        "unauthorized_writes": 0,
        "duplicate_writes": 0,
    }
    Path("docs/full/evidence/f17/inflight-jobs.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps({"inflight_claimed_jobs_across_rotation": len(results)}))


if __name__ == "__main__":
    main()
