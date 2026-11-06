"""Logical Full-only libc transition; original physical volume remains intact.

Run with application services stopped, the original PostgreSQL online, and the
offline encrypted backup already verified. Dumps never leave process memory in
plaintext. A fresh isolated database must match every legacy table fingerprint
before its volume is made available to the rollout script.
"""

import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path

from cryptography.fernet import Fernet


def run(*args, data=None):
    result = subprocess.run(["docker", *args], input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError("Full logical migration failed; original volume retained")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-file", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before_file.read_text(encoding="utf-8-sig"))
    assert before["schema"] == "0017_observability"
    source = "opspilot-full-postgres-1"
    # No app may mutate the snapshot while the two logical dumps are captured.
    for service in ("api", "mcp", "worker", "worker2"):
        assert (
            run("inspect", f"opspilot-full-{service}-1", "--format", "{{.State.Running}}").strip()
            == b"false"
        )
    roles = run("exec", source, "pg_dumpall", "-U", "ops_migration", "--roles-only")
    roles = roles.replace(b"CREATE ROLE ops_migration;", b"-- Bootstrap role already exists.")
    database = run("exec", source, "pg_dump", "-U", "ops_migration", "-Fc", "opspilot_full")
    key = Path(".tools/f17-full-recovery/backup.key").read_bytes()
    nonce = secrets.token_hex(6)
    backup = Path(".tools/f17-full-backup")
    for label, content in (("roles", roles), ("database", database)):
        (backup / f"logical-{nonce}-{label}.enc").write_bytes(Fernet(key).encrypt(content))
    volume = f"opspilot-full-f17-logical-{nonce}"
    container = volume + "-postgres"
    run("volume", "create", volume)
    # Preserve the original bootstrap identity and all existing role credentials.
    run(
        "run",
        "-d",
        "--name",
        container,
        "--network",
        "none",
        "--memory",
        "512m",
        "-e",
        "POSTGRES_USER=ops_migration",
        "-e",
        "POSTGRES_HOST_AUTH_METHOD=trust",
        "-e",
        "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust",
        "--mount",
        f"type=volume,src={volume},dst=/var/lib/postgresql/data",
        "opspilot-full/postgres:f01",
        "postgres",
        "-c",
        "listen_addresses=",
    )
    try:
        for _ in range(120):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_isready",
                    "-U",
                    "ops_migration",
                    "-d",
                    "postgres",
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Fresh logical restore database unavailable")
        run(
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "ops_migration",
            "-d",
            "postgres",
            data=roles,
        )
        run(
            "exec",
            container,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "ops_migration",
            "-d",
            "postgres",
            "-c",
            "CREATE DATABASE opspilot_full OWNER ops_migration TEMPLATE template0 "
            "ENCODING 'UTF8' LOCALE 'C.UTF-8'",
        )
        run(
            "exec",
            "-i",
            container,
            "pg_restore",
            "--exit-on-error",
            "-U",
            "ops_migration",
            "-d",
            "opspilot_full",
            data=database,
        )
        restored = {
            "schema": run(
                "exec",
                container,
                "psql",
                "-XAt",
                "-U",
                "ops_migration",
                "-d",
                "opspilot_full",
                "-c",
                "SELECT version_num FROM workflow.alembic_version",
            )
            .decode()
            .strip()
        }
        # Identical binary ordering to the pre-upgrade fingerprints.
        for table in before:
            if table == "schema":
                continue
            assert table.startswith(("domain.", "workflow.", "checkpoints.")) and all(
                c.isalnum() or c in "_." for c in table
            )
            query = (
                "SELECT json_build_object('count',count(*),'sha256',"
                "encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(t)::text,'' "
                "ORDER BY convert_to(to_jsonb(t)::text,'UTF8')),''),'UTF8')),'hex')) FROM "
                + table
                + " t"
            )
            restored[table] = json.loads(
                run(
                    "exec",
                    container,
                    "psql",
                    "-XAt",
                    "-U",
                    "ops_migration",
                    "-d",
                    "opspilot_full",
                    "-c",
                    query,
                )
            )
        assert restored == before, "Logical restore fingerprint mismatch"
        run(
            "exec",
            container,
            "sed",
            "-i",
            "/^host/s/trust$/scram-sha-256/",
            "/var/lib/postgresql/data/pg_hba.conf",
        )
        Path(".tools/f17-postgres-volume.json").write_text(json.dumps({"volume": volume}) + "\n")
        Path("docs/full/evidence/f17/logical-postgres-restore.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "original_volume_preserved": "opspilot-full_pgdata",
                    "new_volume": volume,
                    "network": "none",
                    "legacy_tables": len(before) - 1,
                    "fingerprints_equal": True,
                    "encrypted_dumps": True,
                    "postgres_major": 16,
                },
                indent=2,
            )
            + "\n"
        )
        print("Full logical restore verified; original physical volume preserved")
    finally:
        run("stop", container)


if __name__ == "__main__":
    main()
