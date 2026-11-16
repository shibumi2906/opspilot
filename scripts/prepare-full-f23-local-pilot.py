"""Prepare an isolated, digest-pinned local TLS pilot; preserve all existing labs."""

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
from pathlib import Path


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="opspilot-full-test-f23-pilot1")
    parser.add_argument("--subnet", type=int, default=70)
    args = parser.parse_args()
    assert re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", args.project)
    assert 65 <= args.subnet <= 96
    root = Path.cwd()
    out = root / ".tools" / args.project
    assert not out.exists(), "Existing pilot credentials preserved; use its compose.json"
    network = ipaddress.ip_network(f"10.245.{args.subnet}.0/24")
    edge = ipaddress.ip_network(f"10.245.{args.subnet + 1}.0/24")
    management = ipaddress.ip_network(f"10.245.{args.subnet + 2}.0/24")
    ids = command("docker", "network", "ls", "-q").split()
    for existing in json.loads(command("docker", "network", "inspect", *ids)):
        for config in existing["IPAM"].get("Config") or []:
            if "Subnet" in config and ":" not in config["Subnet"]:
                assert not any(
                    target.overlaps(ipaddress.ip_network(config["Subnet"]))
                    for target in (network, edge, management)
                ), "Pilot network overlaps"
    tags = {
        "app": "opspilot-full/app:f20",
        "tests": "opspilot-full/tests:f20",
        "web": "opspilot-full/web:f20",
        "browser": "opspilot-full/e2e:f01",
        "postgres": "opspilot-full/postgres:f01",
        "redis": "opspilot-full/redis:f15",
        "oidc": "opspilot-full/oidc:f03",
        "manager": "opspilot-full/manager:f23",
    }
    images = {
        key: json.loads(command("docker", "image", "inspect", tag))[0]["Id"]
        for key, tag in tags.items()
    }
    fingerprint = {
        p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for base in ("src", "migrations")
        for p in Path(base).rglob("*.py")
    }
    code = (
        "import json,hashlib;from pathlib import Path;"
        "print(json.dumps({p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() "
        "for b in ('src','migrations') for p in Path(b).rglob('*.py')}))"
    )
    for key in ("app", "tests"):
        baked = json.loads(
            command(
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "python",
                images[key],
                "-c",
                code,
            )
        )
        assert fingerprint == baked, (
            f"Release image source does not match current checkout; rebuild {key}:f20"
        )
    dist = Path("web/dist")
    assert (dist / "index.html").is_file(), "Build the current web source first"
    web_fingerprint = {
        p.relative_to(dist).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in dist.rglob("*")
        if p.is_file()
    }
    web_baked = dict(
        (line.split(maxsplit=1)[1].removeprefix("./"), line.split(maxsplit=1)[0])
        for line in command(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--entrypoint",
            "sh",
            images["web"],
            "-c",
            "cd /usr/share/nginx/html && find . -type f -exec sha256sum {} +",
        ).splitlines()
    )
    assert all(web_baked.get(p) == digest for p, digest in web_fingerprint.items()), (
        "Release web assets do not match current build; rebuild web:f20"
    )
    assert set(web_baked) - set(web_fingerprint) <= {"50x.html"}, "Stale web assets"
    generator = Path("infra/security/generate_local.py")
    source = (
        generator.read_text()
        .replace("ROOT = Path(__file__).resolve().parents[2]", "ROOT = Path.cwd()")
        .replace(".tools/security-local", ".tools/" + args.project)
    )
    exec(compile(source, str(generator), "exec"), {"__file__": str(generator.resolve())})
    config = json.loads((out / "compose.json").read_text())
    config["name"] = args.project
    config["networks"] = {
        "default": {
            "name": args.project + "_default",
            "internal": True,
            "ipam": {"config": [{"subnet": str(network)}]},
        },
        "edge": {
            "name": args.project + "_edge",
            "ipam": {"config": [{"subnet": str(edge)}]},
        },
    }
    for name, service in config["services"].items():
        imagekey = name if name in images else "tests" if name == "probe" else "app"
        service["image"] = images[imagekey]
        service["pull_policy"] = "never"
        service.setdefault("mem_limit", "768m")
        service.setdefault("cpus", 1.0)
        service.setdefault("pids_limit", 256)
        service.setdefault(
            "logging", {"driver": "local", "options": {"max-size": "5m", "max-file": "3"}}
        )
        if name in {"api", "worker"}:
            service["environment"].update(LLM_MODE="scripted", OPENAI_API_KEY="")
        if name in {"web", "oidc"}:
            service.setdefault("networks", {})["edge"] = {}
        if name in {"worker", "mcp"}:
            service["environment"].update(
                SECRET_MANAGER_URL="https://manager:8200",
                SECRET_MANAGER_CA_FILE="/run/manager-client/ca.crt",
                SECRET_MANAGER_TOKEN_FILE="/run/manager-client/token",
            )
            role = "worker" if name == "worker" else "mcp"
            service["volumes"] += [
                "./manager/ca.crt:/run/manager-client/ca.crt:ro",
                f"./manager/{role}.token:/run/manager-client/token:ro",
            ]
        if name == "worker":
            service["volumes"] = [
                v for v in service["volumes"] if not v.startswith("./service-private:")
            ]
            service["volumes"] += [
                "./service-private/current.pem:/run/service-private/current.pem:ro"
            ]
        if name == "web":
            service.update(
                user="101:101",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs=[
                    "/tmp:rw,nosuid,size=32m",
                    "/var/cache/nginx:rw,nosuid,size=32m,uid=101,gid=101",
                    "/var/run:rw,nosuid,size=1m,uid=101,gid=101",
                ],
            )
        if name in {"probe", "browser"}:
            service["volumes"] = [
                v.replace("../../docs/security/hardening/evidence:/reports", "./reports:/reports")
                for v in service["volumes"]
            ]
    (out / "reports").mkdir()
    (out / "compose.json").write_text(json.dumps(config, indent=2))
    manifest = {
        "project": args.project,
        "target": "owner-approved local TLS pilot",
        "origin": "https://app.opspilot.localhost:8443",
        "issuer": "https://idp.opspilot.localhost:8543/realms/opspilot",
        "images": images,
        "source_sha": command("git", "rev-parse", "HEAD"),
        "dirty": bool(command("git", "status", "--porcelain")),
        "source_sha256": fingerprint,
        "web_dist_sha256": web_fingerprint,
        "network": str(network),
        "edge_network": str(edge),
        "management_network": str(management),
        "model": "scripted",
        "jira_egress": "not enrolled",
        "host_storage_encryption": "unverified; Windows status requires administrator",
    }
    (out / "release-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "prepared": True,
                "project": args.project,
                "images_pinned": len(images),
                "source_files_matched": len(fingerprint),
            }
        )
    )


if __name__ == "__main__":
    main()
