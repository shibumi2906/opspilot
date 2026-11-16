"""Check changed public artifacts against private F20 credentials without exporting values."""

import argparse
import base64
import json
import re
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    args = parser.parse_args()
    if args.project and not re.fullmatch(r"opspilot-full-test-f(?:20|23)-[a-z0-9]+", args.project):
        raise SystemExit("Explicit F20/F23 test project required")
    files = set(
        subprocess.check_output(["git", "diff", "--name-only", "HEAD"], text=True).splitlines()
    )
    files.update(
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], text=True
        ).splitlines()
    )
    files.update(
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "src",
                "tests",
                "scripts",
                ".github",
                "web",
                "migrations",
                "docs/full/evidence/f20",
                "docs/full/evidence/f23/local-pilot-20261116",
            ],
            text=True,
        ).splitlines()
    )
    values = set()
    for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
        key, _, value = line.partition("=")
        if re.search(r"PASSWORD|SECRET|TOKEN|KEY", key):
            values.add(value.strip().strip('"').strip("'"))

    def collect(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {
                    "token",
                    "root_token",
                    "email",
                    "keys",
                    "keys_base64",
                    "raw_secret_base64",
                }:
                    if isinstance(value, str):
                        values.add(value)
                    elif isinstance(value, list):
                        values.update(v for v in value if isinstance(v, str))
                elif isinstance(value, (dict, list)):
                    collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)

    for path in Path(".tools/f20-private").glob("*.json"):
        record = json.loads(path.read_bytes())
        collect(record)
        if "email" in record and "token" in record:
            authorization = (record["email"] + ":" + record["token"]).encode()
            values.add(base64.b64encode(authorization).decode())
    for path in Path(".tools/f20").glob("*/recovery/initialization.json"):
        collect(json.loads(path.read_bytes()))
    for path in [
        *Path(".tools/f20-private").glob("*.txt"),
        *Path(".tools/f20").glob("*/manager/*.token"),
        *Path(".tools/service-keys/private").glob("*.pem"),
        *Path(".tools/f23-pilot-recovery-keys").glob("*/backup.key"),
    ]:
        values.update(path.read_text().splitlines())
    pilot_roots = list(Path(".tools").glob("opspilot-full-test-f23-*"))
    for pilot in pilot_roots:
        if not pilot.is_dir():
            continue
        for name in ("credentials.json", "otp-fixtures.json"):
            path = pilot / name
            if path.is_file():
                values.update(
                    value
                    for value in json.loads(path.read_bytes()).values()
                    if isinstance(value, str)
                )
        for path in pilot.rglob("*"):
            if path.is_file() and path.suffix in {".key", ".pem", ".token", ".dsn"}:
                values.update(path.read_text().splitlines())
        for path in pilot.rglob("initialization.json"):
            collect(json.loads(path.read_bytes()))
        for path in pilot.rglob("credential.json"):
            collect(json.loads(path.read_bytes()))
    needles = [v.encode() for v in values if len(v) >= 8 and not v.startswith("---")]
    matches = []
    for name in files:
        path = Path(name)
        if path.is_file():
            raw = path.read_bytes()
            if any(value in raw for value in needles):
                matches.append(name)
    backlog = "docs/security/asvs-l2-requirement-backlog.json"
    baseline = json.loads(subprocess.check_output(["git", "show", "HEAD:" + backlog]))
    current = json.loads(Path(backlog).read_bytes())
    assert current == baseline and len(current["requirements"]) == 253
    log_matches = jwt_shapes = log_streams = 0
    if args.project:
        base = (
            Path(".tools/f20")
            if args.project.startswith("opspilot-full-test-f20-")
            else Path(".tools")
        )
        lab = base / args.project
        private = lab / "log-scan"
        private.mkdir(parents=True, exist_ok=True)
        for project in (args.project, args.project + "-manager"):
            containers = subprocess.check_output(
                ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project],
                text=True,
                timeout=30,
            ).split()
            for container in containers:
                raw = subprocess.check_output(
                    ["docker", "logs", container], stderr=subprocess.STDOUT, timeout=30
                )
                (private / (container + ".log")).write_bytes(raw)
                log_streams += 1
                log_matches += any(value in raw for value in needles)
                jwt_shapes += len(re.findall(rb"eyJ[\w-]{12,}\.[\w-]{12,}\.[\w-]{12,}", raw))
        for name in ("rehearsal.log", "recovery.log"):
            path = lab / name
            if path.is_file():
                raw = path.read_bytes()
                log_streams += 1
                log_matches += any(value in raw for value in needles)
                jwt_shapes += len(re.findall(rb"eyJ[\w-]{12,}\.[\w-]{12,}\.[\w-]{12,}", raw))
    result = {
        "changed_artifacts_checked": len(files),
        "artifact_secret_matches": len(matches),
        "protected_asvs_records_unchanged": 253,
        "log_streams_checked": log_streams,
        "log_secret_matches": log_matches,
        "log_jwt_shapes": jwt_shapes,
        "scope": (
            "Full env, F20 credentials/recovery/tokens, service keys, generated F23 pilot secrets"
        ),
        "full_asvs_l2": "NOT_MET",
    }
    report = Path(".tools/verification/f20-continuation-artifacts.json")
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if matches or log_matches or jwt_shapes:
        raise SystemExit("Private values detected in candidate artifacts; publication blocked")


if __name__ == "__main__":
    main()
