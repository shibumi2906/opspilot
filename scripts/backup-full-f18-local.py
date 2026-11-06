"""Offline encrypted Full-only pre-upgrade backup and no-network restore verification.

No source volume is written; restore always uses a new volume and no API/workers.
This local Core drill does not replace the F23 deployment/off-host recovery gate.
"""

import argparse
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

from cryptography.fernet import Fernet


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Full-only encrypted recovery operation failed; no raw errors exported")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-file", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before_file.read_text(encoding="utf-8-sig"))
    assert before["schema"] == "0018_lifecycle"
    assert (
        docker("inspect", "opspilot-full-postgres-1", "--format", "{{.State.Running}}") == "false"
    )
    container_meta = json.loads(docker("inspect", "opspilot-full-postgres-1"))[0]
    source_volume = next(
        item["Name"]
        for item in container_meta["Mounts"]
        if item["Destination"] == "/var/lib/postgresql/data"
    )
    assert re.fullmatch(r"opspilot-full-f17-logical-[a-f0-9]{12}", source_volume)
    source_image = container_meta["Image"]
    assert source_image == docker(
        "image", "inspect", "opspilot-full/postgres:f01", "--format", "{{.Id}}"
    )
    private = Path(".tools/f18-full-backup").resolve()
    recovery = Path(".tools/f18-full-recovery").resolve()
    private.mkdir(parents=True, exist_ok=True)
    recovery.mkdir(parents=True, exist_ok=True)
    key = recovery / "backup.key"
    if not key.exists():
        key.write_bytes(Fernet.generate_key())
    nonce = secrets.token_hex(6)
    backup_name = "full-" + nonce + ".tar.gz.enc"
    docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--user",
        "0",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--mount",
        f"type=volume,src={source_volume},dst=/source,readonly",
        "-v",
        str(key) + ":/key:ro",
        "-v",
        str(private) + ":/backup",
        "--entrypoint",
        "python",
        "opspilot-full/app:f01",
        "-c",
        "import io,tarfile;from pathlib import Path;from cryptography.fernet import Fernet;"
        "b=io.BytesIO();t=tarfile.open(fileobj=b,mode='w:gz');t.add('/source',arcname='.');t.close();"
        f"Path('/backup/{backup_name}').write_bytes(Fernet(Path('/key').read_bytes()).encrypt(b.getvalue()))",
    )
    volume = "opspilot-full-f18-recovery-" + nonce
    container = volume + "-postgres"
    docker("volume", "create", volume)
    docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--user",
        "0",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "-v",
        str(key) + ":/key:ro",
        "-v",
        str(private / backup_name) + ":/archive:ro",
        "--mount",
        f"type=volume,src={volume},dst=/restore",
        "--entrypoint",
        "python",
        "opspilot-full/app:f01",
        "-c",
        "import io,tarfile;from pathlib import Path;from cryptography.fernet import Fernet;"
        "raw=Fernet(Path('/key').read_bytes()).decrypt(Path('/archive').read_bytes());"
        "t=tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz');t.extractall('/restore',filter='data')",
    )
    docker(
        "run",
        "-d",
        "--name",
        container,
        "--network",
        "none",
        "--read-only",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--tmpfs",
        "/tmp:rw,nosuid,size=64m",
        "--tmpfs",
        "/var/run/postgresql:rw,nosuid,size=16m",
        "--mount",
        f"type=volume,src={volume},dst=/var/lib/postgresql/data",
        source_image,
        "postgres",
        "-c",
        "listen_addresses=",
    )
    try:
        for _ in range(40):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_isready",
                    "-U",
                    "ops_migration",
                    "-d",
                    "opspilot_full",
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Fresh offline restored database did not become ready")
        restored = {
            "schema": docker(
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
        }
        for table in before:
            if table == "schema":
                continue
            assert re.fullmatch(r"(domain|workflow|identity|checkpoints)\.[a-z_]+", table)
            query = (
                "SELECT json_build_object('count',count(*),'sha256',"
                "encode(sha256(convert_to(COALESCE(" + "string_agg(to_jsonb(t)::text,'' ORDER BY "
                "convert_to(to_jsonb(t)::text,'UTF8')),''),'UTF8')),'hex')) FROM " + table + " t"
            )
            restored[table] = json.loads(
                docker(
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
        assert restored == before, (
            "Restored logical metadata differs; retain all recovery artifacts"
        )
        report = {
            "passed": True,
            "encrypted_backup": True,
            "separate_backup_key": True,
            "source_volume": source_volume,
            "source_offline": True,
            "fresh_restore_volume": volume,
            "restore_network": "none",
            "application_workers": 0,
            "source_schema": before["schema"],
            "all_legacy_table_counts_and_hashes_equal": True,
            "legacy_tables": len(before) - 1,
            "backup_size_bytes": (private / backup_name).stat().st_size,
            "scope": "local Core pre-upgrade only; F23 operational/off-host recovery remains open",
        }
        Path("docs/full/evidence/f18/backup-restore.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(
            json.dumps({"encrypted_backup_restore_passed": True, "legacy_tables": len(before) - 1})
        )
    finally:
        docker("stop", container)


if __name__ == "__main__":
    main()
