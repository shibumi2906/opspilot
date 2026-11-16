"""Encrypted whole-pilot backup and isolated cold restore; never operate on main Full."""

import argparse
import base64
import hashlib
import ipaddress
import json
import runpy
import ssl
import subprocess
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken

helpers = runpy.run_path("scripts/rehearse-full-f23-recovery.py")
docker, query, snapshot, assert_fixture = (
    helpers[k] for k in ("docker", "query", "snapshot", "assert_fixture")
)


def compose(root, project, *args, manager=False):
    config = root / ("manager/compose.json" if manager else "compose.json")
    name = project + "-manager" if manager else project
    result = subprocess.run(
        ["docker", "compose", "-p", name, "-f", str(config), *args],
        capture_output=True,
        timeout=240,
    )
    with (root / "recovery.log").open("ab") as log:
        log.write(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Pilot recovery container step failed; see private recovery.log")


def volumes(project, config, manager=False):
    prefix = project + ("-manager" if manager else "")
    return {key: prefix + "_" + key for key in config["volumes"] if key != "pgdata"}


def refresh_manager(root):
    state = json.loads((root / "manager-recovery/initialization.json").read_bytes())
    with httpx.Client(
        base_url="https://127.0.0.1:18270",
        trust_env=False,
        timeout=5,
        verify=ssl.create_default_context(cafile=str(root / "manager/ca.crt")),
    ) as client:

        def call(method, path, body=None):
            response = client.request(
                method, "/v1/" + path, json=body, headers={"X-Vault-Token": state["root_token"]}
            )
            if response.status_code != 200:
                raise RuntimeError("Recovered manager request denied; response withheld")
            return response.json()

        for _ in range(45):
            try:
                sealed = call("GET", "sys/seal-status")["sealed"]
                break
            except (httpx.HTTPError, RuntimeError):
                time.sleep(1)
        else:
            raise RuntimeError("Recovered manager unavailable")
        if sealed:
            for share in state["keys"][:2]:
                call("PUT", "sys/unseal", {"key": share})
        for _ in range(30):
            if client.get("/v1/sys/health").status_code == 200:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Recovered manager leader unavailable")
        for role in ("worker", "mcp"):
            policy = "f17-" + role
            before = call("GET", "sys/policies/acl/" + policy)["data"]["policy"]
            record = call(
                "POST",
                "auth/token/create",
                {
                    "policies": [policy],
                    "no_default_policy": True,
                    "ttl": "1h",
                    "explicit_max_ttl": "1h",
                    "renewable": False,
                },
            )
            (root / "manager" / (role + ".token")).write_text(record["auth"]["client_token"])
            assert call("GET", "sys/policies/acl/" + policy)["data"]["policy"] == before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backup", "restore"))
    parser.add_argument("--source", default="opspilot-full-test-f23-pilot2")
    parser.add_argument("--target", default="opspilot-full-test-f23-recovery1")
    parser.add_argument("--subnet", type=int, default=76)
    parser.add_argument("--image-overrides", type=Path)
    args = parser.parse_args()
    import re

    for project in (args.source, args.target):
        assert re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", project)
    assert args.source != args.target and 65 <= args.subnet <= 96
    source = Path(".tools") / args.source
    target = Path(".tools") / args.target
    manifest = json.loads((source / "release-manifest.json").read_bytes())
    assert manifest["model"] == "scripted"
    image = manifest["images"]["app"]
    archives = Path(".tools/f23-pilot-backups") / args.source
    keys = Path(".tools/f23-pilot-recovery-keys") / args.source
    report = Path("docs/full/evidence/f23/local-pilot-20261116")
    report.mkdir(parents=True, exist_ok=True)
    archive, keyfile = archives / "pilot.enc", keys / "backup.key"
    database = "opspilot_full_test"
    source_pg, target_pg = args.source + "-postgres-1", args.target + "-postgres-1"
    if args.mode == "backup":
        assert args.image_overrides is None
        fixtures = list((source / "reports").glob("Fixture-*/recovery-fixture.json"))
        assert len(fixtures) == 1
        fixture = json.loads(fixtures[0].read_bytes())
        assert (
            query(
                source_pg, database, "SELECT count(*) FROM integrations.jira_bindings WHERE enabled"
            )
            == "0"
        )
        compose(
            source,
            args.source,
            "stop",
            "--timeout",
            "30",
            "api",
            "worker",
            "mcp",
            "web",
            "collector",
            "oidc",
        )
        compose(source, args.source, "stop", manager=True)
        assert_fixture(source_pg, database, fixture)
        source_schema = query(
            source_pg, database, "SELECT version_num FROM workflow.alembic_version"
        )
        assert source_schema == "0023_jira_audit"
        before = snapshot(source_pg, database)
        dump = docker("exec", source_pg, "pg_dump", "-Fc", "-U", "ops_migration", database)
        compose(source, args.source, "stop")
        config = json.loads((source / "compose.json").read_bytes())
        manager = json.loads((source / "manager/compose.json").read_bytes())
        volume_map = {"app:" + k: v for k, v in volumes(args.source, config).items()}
        volume_map.update(
            {"manager:" + k: v for k, v in volumes(args.source, manager, manager=True).items()}
        )
        raw_volumes = {}
        tar_code = (
            "import io,tarfile,sys; b=io.BytesIO();"
            "t=tarfile.open(fileobj=b,mode='w:gz');t.add('/source',arcname='.');"
            "t.close();sys.stdout.buffer.write(b.getvalue())"
        )
        for label, volume in volume_map.items():
            raw_volumes[label] = base64.b64encode(
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
                    image,
                    "-c",
                    tar_code,
                )
            ).decode()
        private = {
            path.relative_to(source).as_posix(): base64.b64encode(path.read_bytes()).decode()
            for path in source.rglob("*")
            if path.is_file()
            and "reports" not in path.relative_to(source).parts
            and path.suffix != ".log"
        }
        bundle = {
            "source": args.source,
            "private": private,
            "volumes": raw_volumes,
            "dump": base64.b64encode(dump).decode(),
            "snapshot": before,
            "fixture": fixture,
        }
        archives.mkdir(parents=True)
        keys.mkdir(parents=True)
        key = Fernet.generate_key()
        with keyfile.open("xb") as handle:
            handle.write(key)
        encrypted = Fernet(key).encrypt(json.dumps(bundle).encode())
        with archive.open("xb") as handle:
            handle.write(encrypted)
        result = {
            "passed": True,
            "source": args.source,
            "tables": len(before),
            "named_volume_archives": len(raw_volumes),
            "encrypted_bytes": len(encrypted),
            "encrypted_sha256": hashlib.sha256(encrypted).hexdigest(),
            "key_separate_directory": True,
            "source_writers_stopped": True,
            "source_schema": source_schema,
            "off_host_copy": False,
        }
        with (report / ("whole-pilot-backup-" + args.source + ".json")).open("x") as handle:
            json.dump(result, handle, indent=2)
        print(json.dumps(result))
        return

    started = time.monotonic()
    assert not target.exists(), "Existing recovery state must not be overwritten"
    nets = [ipaddress.ip_network(f"10.245.{args.subnet + n}.0/24") for n in range(3)]
    ids = docker("network", "ls", "-q").decode().split()
    for network in json.loads(docker("network", "inspect", *ids)):
        for config in network["IPAM"].get("Config") or []:
            if "Subnet" in config and ":" not in config["Subnet"]:
                assert not any(n.overlaps(ipaddress.ip_network(config["Subnet"])) for n in nets)
    encrypted = archive.read_bytes()
    try:
        Fernet(Fernet.generate_key()).decrypt(encrypted)
    except InvalidToken:
        pass
    else:
        raise AssertionError("Unrelated backup key accepted")
    bundle = json.loads(Fernet(keyfile.read_bytes()).decrypt(encrypted))
    assert bundle["source"] == args.source
    target.mkdir()
    for name, value in bundle["private"].items():
        path = target / name
        assert path.resolve().is_relative_to(target.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(value))
    (target / "reports").mkdir()
    (target / "recovery-fixture.json").write_text(json.dumps(bundle["fixture"]))
    config = json.loads((target / "compose.json").read_bytes())
    source_manifest = json.loads((target / "release-manifest.json").read_bytes())
    overrides = {}
    if args.image_overrides:
        overrides = json.loads(args.image_overrides.read_bytes())
        assert set(overrides) <= {"web", "postgres", "redis", "oidc", "manager"}
        assert all(re.fullmatch(r"sha256:[a-f0-9]{64}", value) for value in overrides.values())
        manifest = {**manifest, "images": {**manifest["images"], **overrides}}
        for role in ("web", "postgres", "redis", "oidc"):
            if role in overrides:
                config["services"][role]["image"] = overrides[role]
    config["name"] = args.target
    config["networks"]["default"].update(name=args.target + "_default")
    config["networks"]["default"]["ipam"]["config"] = [{"subnet": str(nets[0])}]
    config["networks"]["edge"].update(name=args.target + "_edge")
    config["networks"]["edge"]["ipam"]["config"] = [{"subnet": str(nets[1])}]
    assert config["networks"]["default"]["internal"] is True
    passwords = json.loads((target / "credentials.json").read_bytes())
    role_sql = []
    for role in ("workflow", "domain", "checkpoint", "identity"):
        password = passwords[role]
        assert re.fullmatch(r"[a-f0-9]{64}", password)
        role_sql.append(f"CREATE ROLE ops_{role} NOLOGIN PASSWORD '{password}';")
    role_sql.append("CREATE ROLE ops_ingress NOLOGIN;")
    (target / "recovery-roles.sql").write_text("\n".join(role_sql) + "\n")
    config["services"]["postgres"]["volumes"] = [
        "./recovery-roles.sql:/docker-entrypoint-initdb.d/001-roles.sql:ro"
        if "/docker-entrypoint-initdb.d/" in mount
        else mount
        for mount in config["services"]["postgres"]["volumes"]
    ]
    (target / "compose.json").write_text(json.dumps(config, indent=2))
    manager = json.loads((target / "manager/compose.json").read_bytes())
    if "manager" in overrides:
        manager["services"]["manager"]["image"] = overrides["manager"]
    manager["name"] = args.target + "-manager"
    manager["networks"]["default"]["name"] = args.target + "_default"
    manager["networks"]["management"]["ipam"]["config"] = [{"subnet": str(nets[2])}]
    manager["services"]["manager"]["volumes"] = [
        v.replace(source.resolve().as_posix(), target.resolve().as_posix())
        for v in manager["services"]["manager"]["volumes"]
    ]
    (target / "manager/compose.json").write_text(json.dumps(manager, indent=2))
    (target / "source-release-manifest.json").write_text(json.dumps(source_manifest, indent=2))
    recovered_manifest = {
        **manifest,
        "project": args.target,
        "restored_from_project": args.source,
        "network": str(nets[0]),
        "edge_network": str(nets[1]),
        "management_network": str(nets[2]),
        "encrypted_backup_sha256": hashlib.sha256(encrypted).hexdigest(),
    }
    (target / "release-manifest.json").write_text(json.dumps(recovered_manifest, indent=2))
    for digest in manifest["images"].values():
        docker("image", "inspect", digest)
    compose(target, args.target, "up", "-d", "--wait", "--no-build", "postgres", "redis")
    assert (
        query(
            target_pg,
            database,
            "SELECT count(*) FROM pg_tables WHERE "
            "schemaname NOT IN ('pg_catalog','information_schema')",
        )
        == "0"
    )
    docker(
        "exec",
        "-i",
        target_pg,
        "pg_restore",
        "--exit-on-error",
        "--single-transaction",
        "-U",
        "ops_migration",
        "-d",
        database,
        data=base64.b64decode(bundle["dump"]),
    )
    query(target_pg, "postgres", f"ALTER DATABASE {database} SET default_transaction_read_only=on")
    roles = ("ops_workflow", "ops_domain", "ops_checkpoint", "ops_identity", "ops_ingress")
    for role in roles:
        query(target_pg, "postgres", f"ALTER ROLE {role} NOLOGIN")
    assert snapshot(target_pg, database) == bundle["snapshot"]
    assert_fixture(target_pg, database, bundle["fixture"])
    assert (
        query(target_pg, database, "SELECT count(*) FROM integrations.jira_bindings WHERE enabled")
        == "0"
    )
    offline_seconds = round(time.monotonic() - started, 2)
    extract = (
        "import io,sys,tarfile,os;from pathlib import Path;"
        "t=tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz');"
        "members=t.getmembers();assert not any(m.issym() or m.islnk() for m in members);"
        "t.extractall('/target',filter='data');"
        "[(os.chown('/target/'+m.name,m.uid,m.gid)) for m in members]"
    )
    app_volumes = volumes(args.target, config)
    manager_volumes = volumes(args.target, manager, manager=True)
    for label, raw in bundle["volumes"].items():
        category, name = label.split(":")
        volume = (app_volumes if category == "app" else manager_volumes)[name]
        project = args.target if category == "app" else args.target + "-manager"
        docker(
            "volume",
            "create",
            "--label",
            "com.docker.compose.project=" + project,
            "--label",
            "com.docker.compose.volume=" + name,
            volume,
        )
        docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0",
            "--mount",
            f"type=volume,src={volume},dst=/target",
            "--entrypoint",
            "python",
            image,
            "-c",
            extract,
            data=base64.b64decode(raw),
        )
    for role in roles:
        query(target_pg, "postgres", f"ALTER ROLE {role} LOGIN")
    query(target_pg, "postgres", f"ALTER DATABASE {database} SET default_transaction_read_only=off")
    compose(target, args.target, "up", "-d", "--no-build", manager=True)
    refresh_manager(target)
    compose(
        target,
        args.target,
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
        "--no-build",
        "oidc",
        "collector",
        "mcp",
        "api",
        "worker",
        "web",
    )
    compose(
        target,
        args.target,
        "run",
        "--rm",
        "--no-deps",
        "browser",
        "node",
        "/work/scripts/security_pilot_restore_browser.mjs",
    )
    assert int(query(target_pg, database, "SELECT count(*) FROM domain.tickets")) == (
        bundle["snapshot"]["domain.tickets"]["rows"] + 1
    )
    result = {
        "passed": True,
        "source": args.source,
        "target": args.target,
        "tables_matched_before_writes": len(bundle["snapshot"]),
        "offline_reconciliation_seconds": offline_seconds,
        "full_cold_restore_seconds": round(time.monotonic() - started, 2),
        "scope": (
            "key retrieval, decryption, config/volumes/empty DB, manager unseal/token refresh, "
            "IdP, services and browser approval smoke; images preloaded"
        ),
        "egress": "business services internal-only; no Jira enrollment",
        "committed_extra_tickets": 0,
        "pending_new_tickets": 1,
        "host_storage_encryption": "unverified",
        "full_asvs_l2": "NOT_MET",
    }
    result["rto_target_met"] = result["full_cold_restore_seconds"] <= 3600
    with (report / ("whole-pilot-restore-" + args.target + ".json")).open("x") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
