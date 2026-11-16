"""Repeatable encrypted, quiesced backup for the explicitly selected local Full pilot.

No provider requests, source database migrations, volume removal or implicit job replay.
Keys, archives, catalog and detailed logs remain local and ignored.
"""

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import runpy
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
HELPERS = runpy.run_path(str(ROOT / "scripts/rehearse-full-f23-pilot-recovery.py"))
docker = HELPERS["docker"]
query = HELPERS["query"]
snapshot = HELPERS["snapshot"]
compose = HELPERS["compose"]


def confined(value, parent):
    path = Path(value).resolve()
    if not path.is_relative_to(parent.resolve()) or path == parent.resolve():
        raise ValueError("Backup path escapes its explicitly owned directory")
    return path


@lru_cache(maxsize=1)
def windows_owner_sid():
    raw = subprocess.check_output(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=30,
    )
    row = next(csv.reader(raw.decode("utf-8", errors="replace").splitlines()))
    sid = row[1]
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise ValueError("Cannot establish the local recovery-file owner")
    return sid


def private_directory(path):
    path = confined(path, ROOT / ".tools")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        # Replace the DACL, not merely inherited entries: pre-existing explicit
        # grants must not silently retain access to recovery keys or plaintext config.
        literal_path = str(path).replace("'", "''")
        command = (
            "$ErrorActionPreference='Stop';"
            "$acl=[Security.AccessControl.DirectorySecurity]::new();"
            "$acl.SetAccessRuleProtection($true,$false);"
            "foreach($sid in @('" + windows_owner_sid() + "','S-1-5-18','S-1-5-32-544')){"
            "$identity=[Security.Principal.SecurityIdentifier]::new($sid);"
            "$rule=[Security.AccessControl.FileSystemAccessRule]::new($identity,"
            "'FullControl','ContainerInherit,ObjectInherit','None','Allow');"
            "$acl.AddAccessRule($rule)};"
            "[IO.Directory]::SetAccessControl('" + literal_path + "',$acl)"
        )
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                base64.b64encode(command.encode("utf-16le")).decode(),
            ],
            check=True,
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        path.chmod(0o700)
    return path


def require_fresh_docker_target(target):
    for arguments in (
        ("ps", "-aq", "--filter", "label=com.docker.compose.project=" + target),
        ("ps", "-aq", "--filter", "name=" + target + "-"),
        ("volume", "ls", "-q", "--filter", "name=" + target + "_"),
    ):
        if docker(*arguments).strip():
            raise ValueError("Existing recovery Docker state preserved; choose a fresh target")


def retention_plan(records, now):
    """Keep latest seven UTC dates and four ISO weeks, plus held/incomplete copies."""
    ordered = sorted(records, key=lambda r: r["created_at_utc"], reverse=True)
    days, weeks, keep = set(), set(), set()
    for row in ordered:
        stamp = datetime.fromisoformat(row["created_at_utc"])
        if stamp.tzinfo is None or stamp > now + timedelta(minutes=5):
            raise ValueError("Invalid backup clock; retention cannot safely proceed")
        day, week = stamp.date(), stamp.isocalendar()[:2]
        if row.get("hold") or row.get("state") != "verified":
            keep.add(row["id"])
        if day not in days and len(days) < 7:
            days.add(day)
            keep.add(row["id"])
        if week not in weeks and len(weeks) < 4:
            weeks.add(week)
            keep.add(row["id"])
    return {"keep": sorted(keep), "remove": sorted(r["id"] for r in records if r["id"] not in keep)}


class Store:
    def __init__(self, config_path):
        self.config_path = confined(config_path, ROOT / ".tools")
        self.config = json.loads(self.config_path.read_bytes())
        self.project = self.config["project"]
        if not re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", self.project):
            raise ValueError("Explicit isolated pilot required")
        self.private = ROOT / ".tools" / self.project
        self.archives = confined(self.config["archive_root"], ROOT / ".tools")
        self.keys = confined(self.config["key_root"], ROOT / ".tools")
        if (
            self.archives == self.keys
            or self.archives.is_relative_to(self.keys)
            or self.keys.is_relative_to(self.archives)
        ):
            raise ValueError("Recovery keys and archive directories must be separate")
        private_directory(self.archives)
        private_directory(self.keys)
        self.catalog = self.archives / "catalog.json"
        self.journal = self.archives / "interrupted-operation.json"
        self.lock_path = self.archives / "operation.lock"
        self.lock = None

    def __enter__(self):
        # OS file handle lock: process death releases it, unlike a stale exclusive marker.
        self.lock = self.lock_path.open("a+b")
        # Windows denies reads of another process's locked byte. Check size without
        # reading that byte, then retry lock acquisition rather than leaking a handle.
        if self.lock_path.stat().st_size == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        deadline = time.monotonic() + self.config.get("lock_timeout_seconds", 600)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    self.lock.close()
                    raise
                time.sleep(1)
        return self

    def __exit__(self, *_):
        if self.lock:
            self.lock.close()

    def records(self):
        if not self.catalog.exists():
            return []
        rows = json.loads(self.catalog.read_bytes())["backups"]
        if len(rows) != len({r["id"] for r in rows}):
            raise ValueError("Duplicate backup identities in catalog")
        return rows

    def save(self, rows):
        temporary = self.catalog.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "project": self.project, "backups": rows}, indent=2)
        )
        temporary.replace(self.catalog)

    def paths(self, identifier):
        if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{12}", identifier):
            raise ValueError("Invalid backup identity")
        return self.archives / (identifier + ".enc"), self.keys / (identifier + ".key")

    def load(self, row):
        archive, keyfile = self.paths(row["id"])
        if archive.stat().st_size > self.config.get("max_encrypted_bytes", 268435456):
            raise ValueError("Archive exceeds reviewed in-memory recovery limit")
        raw = archive.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["encrypted_sha256"]:
            raise ValueError("Archive checksum mismatch; preserve for investigation")
        bundle = json.loads(Fernet(keyfile.read_bytes()).decrypt(raw))
        if bundle["metadata"] != {k: v for k, v in row.items() if k != "encrypted_sha256"}:
            raise ValueError("Catalog differs from authenticated backup metadata")
        return bundle

    def running(self, manager=False):
        project = self.project + "-manager" if manager else self.project
        ids = (
            docker("ps", "-q", "--filter", "label=com.docker.compose.project=" + project)
            .decode()
            .split()
        )
        if not ids:
            return []
        return [
            r["Config"]["Labels"]["com.docker.compose.service"]
            for r in json.loads(docker("inspect", *ids))
        ]

    def resume_services(self, application, manager):
        allowed = {
            "web",
            "api",
            "worker",
            "worker2",
            "mcp",
            "collector",
            "oidc",
            "postgres",
            "redis",
        }
        if set(application) - allowed or manager not in ([], ["manager"]):
            raise ValueError("Unexpected service in recovery journal; operator review required")
        if manager:
            compose(self.private, self.project, "up", "-d", "--no-build", manager=True)
            HELPERS["refresh_manager"](self.private)
        if application:
            compose(
                self.private,
                self.project,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "120",
                "--no-deps",
                "--no-build",
                *application,
            )
        if set(self.running()) != set(application):
            raise ValueError("Previously running application services did not resume")
        if self.running(manager=True) != manager:
            raise ValueError("Previously running manager did not resume")

    def recover_interrupted(self):
        if not self.journal.exists():
            return False
        state = json.loads(self.journal.read_bytes())
        if state["project"] != self.project:
            raise ValueError("Foreign operation journal; preserved for operator review")
        self.validate_profile()
        self.resume_services(state["application"], state["manager"])
        self.journal.unlink()
        return True

    def record_services(self, application, manager):
        # Persist before stopping anything; process/host death must not lose resume intent.
        with self.journal.open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "project": self.project,
                    "application": application,
                    "manager": manager,
                    "started_at_utc": datetime.now(UTC).isoformat(),
                },
                handle,
            )
            handle.flush()
            os.fsync(handle.fileno())

    def validate_profile(self):
        config = json.loads((self.private / "compose.json").read_bytes())
        manager = json.loads((self.private / "manager/compose.json").read_bytes())
        manifest = json.loads((self.private / "release-manifest.json").read_bytes())
        if config["name"] != self.project or manifest["project"] != self.project:
            raise ValueError("Pilot configuration identity mismatch")
        if manifest["model"] != "scripted" or not config["networks"]["default"]["internal"]:
            raise ValueError(
                "Only the reviewed scripted/internal pilot can use this deployment policy"
            )
        if any(
            config["services"][r]["environment"].get("LLM_MODE") != "scripted"
            for r in ("api", "worker")
        ):
            raise ValueError("Paid/real execution forbidden")
        pg, database = self.project + "-postgres-1", "opspilot_full_test"
        if (
            query(pg, database, "SELECT count(*) FROM integrations.jira_bindings WHERE enabled")
            != "0"
        ):
            raise ValueError(
                "External-write enrollment changed; review operational profile before proceeding"
            )
        return config, manager, manifest

    def backup(self):
        config, manager, manifest = self.validate_profile()
        pg, database = self.project + "-postgres-1", "opspilot_full_test"
        app_running, manager_running = self.running(), self.running(manager=True)
        if set(app_running) - {
            "web",
            "api",
            "worker",
            "worker2",
            "mcp",
            "collector",
            "oidc",
            "postgres",
            "redis",
        }:
            raise ValueError("An operator tool is running; do not quiesce or restart it implicitly")
        if manager_running != ["manager"]:
            raise ValueError("Reviewed manager must already be running")
        if "postgres" not in app_running:
            raise ValueError(
                "Source PostgreSQL must already be running; no implicit source startup"
            )
        identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(6)
        metadata = {
            "id": identifier,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "state": "verified",
            "hold": False,
            "project": self.project,
        }
        archive, keyfile = self.paths(identifier)
        self.record_services(app_running, manager_running)
        try:
            writers = [
                r
                for r in ("web", "api", "worker", "worker2", "mcp", "collector", "oidc")
                if r in app_running
            ]
            if writers:
                compose(self.private, self.project, "stop", "--timeout", "30", *writers)
            if manager_running:
                compose(self.private, self.project, "stop", manager=True)
            before = snapshot(pg, database)
            dump = docker("exec", pg, "pg_dump", "-Fc", "-U", "ops_migration", database)
            if snapshot(pg, database) != before:
                raise ValueError("Source changed during consistent backup window")
            counts = json.loads(
                query(
                    pg,
                    database,
                    "SELECT json_build_object('pending', (SELECT count(*) FROM workflow.agent_runs "
                    "WHERE status='waiting_for_approval'), 'unknown', (SELECT count(*) FROM "
                    "integrations.jira_operations WHERE outcome='unknown'))",
                )
            )
            metadata["hold"] = counts["unknown"] > 0
            volume_map = {
                "app:" + k: v for k, v in HELPERS["volumes"](self.project, config).items()
            }
            volume_map.update(
                {
                    "manager:" + k: v
                    for k, v in HELPERS["volumes"](self.project, manager, manager=True).items()
                }
            )
            tar_code = (
                "import io,tarfile,sys;b=io.BytesIO();t=tarfile.open(fileobj=b,mode='w:gz');"
                "t.add('/source',arcname='.');t.close();sys.stdout.buffer.write(b.getvalue())"
            )
            archived_volumes = {}
            for label, volume in volume_map.items():
                if not volume.startswith(
                    self.project + ("-manager_" if label.startswith("manager:") else "_")
                ):
                    raise ValueError("Foreign volume forbidden")
                archived_volumes[label] = base64.b64encode(
                    docker(
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--read-only",
                        "--user",
                        "0",
                        "--mount",
                        f"type=volume,src={volume},dst=/source,readonly",
                        "--entrypoint",
                        "python",
                        manifest["images"]["app"],
                        "-c",
                        tar_code,
                    )
                ).decode()
            private = {
                p.relative_to(self.private).as_posix(): base64.b64encode(p.read_bytes()).decode()
                for p in self.private.rglob("*")
                if p.is_file()
                and "reports" not in p.relative_to(self.private).parts
                and "log-scan" not in p.relative_to(self.private).parts
                and p.suffix != ".log"
            }
            bundle = {
                "version": 1,
                "metadata": metadata,
                "snapshot": before,
                "counts": counts,
                "dump": base64.b64encode(dump).decode(),
                "volumes": archived_volumes,
                "private": private,
                "manifest": manifest,
            }
            key = Fernet.generate_key()
            raw = Fernet(key).encrypt(json.dumps(bundle).encode())
            if len(raw) > self.config.get("max_encrypted_bytes", 268435456):
                raise ValueError("Backup exceeds reviewed resource limit")
            with keyfile.open("xb") as handle:
                handle.write(key)
            with archive.open("xb") as handle:
                handle.write(raw)
            row = {**metadata, "encrypted_sha256": hashlib.sha256(raw).hexdigest()}
            self.load(row)
            rows = self.records() + [row]
            self.save(rows)
        finally:
            # Resume exactly the previously running services; never start a stopped worker.
            self.resume_services(app_running, manager_running)
            self.journal.unlink()
        # A backup isn't operationally successful unless all former services resumed.
        if set(self.running()) != set(app_running):
            raise ValueError("Backup captured, but original application state was not restored")
        return {
            "passed": True,
            "backup_id": identifier,
            "tables": len(before),
            "volume_archives": len(archived_volumes),
            "source_counts": counts,
            "encrypted_bytes": len(raw),
            "source_services_resumed": True,
        }

    def refresh_identities(self):
        services = self.running()
        if "postgres" not in services or self.running(manager=True) != ["manager"]:
            return {"skipped": True, "reason": "pilot intentionally stopped; no implicit startup"}
        self.validate_profile()
        stopped = [r for r in ("worker", "worker2") if r in services]
        self.record_services(services, ["manager"])
        try:
            if stopped:
                compose(self.private, self.project, "stop", "--timeout", "30", *stopped)
        finally:
            self.resume_services(services, ["manager"])
            self.journal.unlink()
        return {
            "passed": True,
            "identities_refreshed": ["worker", "mcp"],
            "existing_keys_and_acl_preserved": True,
        }

    def prune(self, apply=False):
        rows = self.records()
        # Validate every artifact and key before planning any deletion.
        for row in rows:
            self.load(row)
        plan = retention_plan(rows, datetime.now(UTC))
        if apply:
            survivors = [row for row in rows if row["id"] in plan["keep"]]
            self.save(survivors)
            for identifier in plan["remove"]:
                archive, keyfile = self.paths(identifier)
                # Single explicitly owned files only, never a recursive directory operation.
                confined(archive, self.archives).unlink()
                confined(keyfile, self.keys).unlink()
        return {"applied": apply, **plan}

    def verify_restore(self, identifier, target):
        if not re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", target) or target == self.project:
            raise ValueError("Fresh independent recovery project required")
        require_fresh_docker_target(target)
        row = next(r for r in self.records() if r["id"] == identifier)
        bundle = self.load(row)
        directory = ROOT / ".tools/full-backup-verification" / target
        if directory.exists():
            raise ValueError("Existing recovery state preserved; choose a fresh target")
        private_directory(directory.parent)
        private_directory(directory)
        password = secrets.token_hex(32)
        config = {
            "name": target,
            "services": {
                "postgres": {
                    "image": bundle["manifest"]["images"]["postgres"],
                    "pull_policy": "never",
                    "network_mode": "none",
                    "mem_limit": "768m",
                    "cpus": 1.0,
                    "command": ["postgres", "-c", "listen_addresses="],
                    "environment": {
                        "POSTGRES_USER": "ops_migration",
                        "POSTGRES_DB": "opspilot_full_recovered",
                        "POSTGRES_PASSWORD": password,
                    },
                    "volumes": [
                        "recovery:/var/lib/postgresql/data",
                        str(ROOT / "infra/postgres/f23-recovery-roles.sql")
                        + ":/docker-entrypoint-initdb.d/001-roles.sql:ro",
                    ],
                    "healthcheck": {
                        "test": [
                            "CMD-SHELL",
                            "pg_isready -U ops_migration -d opspilot_full_recovered",
                        ],
                        "interval": "2s",
                        "retries": 30,
                    },
                }
            },
            "volumes": {"recovery": {}},
        }
        path = directory / "compose.json"
        path.write_text(json.dumps(config, indent=2))
        cli = ["docker", "compose", "-p", target, "-f", str(path)]
        try:
            subprocess.run(
                cli + ["up", "-d", "--wait", "--no-build"],
                check=True,
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            container, database = target + "-postgres-1", "opspilot_full_recovered"
            assert (
                query(
                    container,
                    database,
                    "SELECT count(*) FROM pg_tables "
                    "WHERE schemaname NOT IN ('pg_catalog','information_schema')",
                )
                == "0"
            )
            docker(
                "exec",
                "-i",
                container,
                "pg_restore",
                "--single-transaction",
                "--exit-on-error",
                "-U",
                "ops_migration",
                "-d",
                database,
                data=base64.b64decode(bundle["dump"]),
            )
            query(
                container,
                "postgres",
                "ALTER DATABASE opspilot_full_recovered SET default_transaction_read_only=on",
            )
            assert snapshot(container, database) == bundle["snapshot"]
            assert (
                docker("inspect", container, "--format", "{{.HostConfig.NetworkMode}}").strip()
                == b"none"
            )
            assert (
                query(
                    container,
                    database,
                    "SELECT count(*) FROM pg_roles WHERE rolname IN "
                    "('ops_workflow','ops_domain','ops_checkpoint','ops_identity','ops_ingress') "
                    "AND rolcanlogin",
                )
                == "0"
            )
            # Exercise all volume payloads and private files without extracting secrets.
            import io
            import tarfile

            for raw in bundle["volumes"].values():
                with tarfile.open(fileobj=io.BytesIO(base64.b64decode(raw)), mode="r:gz") as tar:
                    assert tar.getmembers()
            assert "admin-mfa/credential.json" in bundle["private"]
            return {
                "passed": True,
                "backup_id": identifier,
                "target": target,
                "tables_matched": len(bundle["snapshot"]),
                "source_counts": bundle["counts"],
                "egress": "none",
                "application_roles": "NOLOGIN",
                "read_only": True,
                "volume_payloads_verified": len(bundle["volumes"]),
                "source_modified": False,
            }
        finally:
            subprocess.run(
                cli + ["stop"],
                check=True,
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("backup", "retention", "restore-verify", "status", "refresh-identities")
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--id")
    parser.add_argument("--target")
    args = parser.parse_args()
    with Store(args.config) as store:
        recovered = (
            store.recover_interrupted() if args.mode in {"backup", "refresh-identities"} else False
        )
        if args.mode == "backup":
            result = store.backup()
            result["retention"] = store.prune(apply=True)
        elif args.mode == "retention":
            result = store.prune(apply=args.apply)
        elif args.mode == "restore-verify":
            result = store.verify_restore(args.id, args.target)
        elif args.mode == "refresh-identities":
            result = store.refresh_identities()
        else:
            rows = store.records()
            for row in rows:
                store.load(row)
            age = (
                (
                    datetime.now(UTC)
                    - max(datetime.fromisoformat(row["created_at_utc"]) for row in rows)
                ).total_seconds()
                if rows
                else None
            )
            result = {
                "backups": len(rows),
                "latest_age_seconds": age,
                "within_24h": age is not None and 0 <= age <= 86400,
            }
            result["passed"] = result["within_24h"]
        result["recovered_interrupted_operation"] = recovered
    output = ROOT / ".tools/full-backup-operations" / store.project
    private_directory(output.parent)
    private_directory(output)
    result["completed_at_utc"] = datetime.now(UTC).isoformat()
    (output / ("last-" + args.mode + ".json")).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    if result.get("passed") is False:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        log = ROOT / ".tools/full-backup-errors"
        private_directory(log)
        (
            log / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4) + ".log")
        ).write_text(traceback.format_exc())
        print(
            json.dumps(
                {
                    "passed": False,
                    "error_type": type(error).__name__,
                    "reason": "Backup operation failed; private evidence retained",
                }
            )
        )
        sys.exit(1)
