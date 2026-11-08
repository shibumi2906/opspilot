"""Local exact-secret checks of candidate artifacts and labelled F21 runtime logs.

Only counts and scope enter the public report. Private raw logs remain ignored.
"""

import base64
import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
EVIDENCE = ROOT / "docs/full/evidence/f21"
PRIVATE = ROOT / ".tools/f21-private-logs"


def main() -> int:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    values: set[bytes] = set()
    for line in (ROOT / ".env").read_text().splitlines():
        key, sep, raw = line.partition("=")
        if sep and any(k in key.upper() for k in ("PASSWORD", "SECRET", "TOKEN", "KEY")):
            raw = raw.strip().strip('"').strip("'")
            if len(raw) >= 20:
                values.add(raw.encode())
    for directory in (
        ROOT / ".tools/f21",
        ROOT / ".tools/observability-test",
        ROOT / ".tools/cache-test",
        ROOT / ".tools/service-keys/private",
    ):
        for path in directory.rglob("*"):
            if path.is_file() and (
                path.suffix in {".token", ".key", ".pem"}
                or path.name in {"token", "password", "signing-key"}
            ):
                raw = path.read_bytes().strip().replace(b"\r\n", b"\n")
                if len(raw) >= 20:
                    values.add(raw)
    for path in (ROOT / ".tools/f21").rglob("initialization.json"):
        record = json.loads(path.read_text())
        for raw in [
            record.get("root_token", ""),
            *record.get("keys", []),
            *record.get("keys_base64", []),
        ]:
            if len(raw) >= 20:
                values.add(raw.encode())
    for path in (ROOT / ".tools/cache-test/password", ROOT / ".tools/cache-test/signing-key"):
        if path.is_file():
            values.add(path.read_bytes().strip())
    # This credential is not mounted in the F21 lab, but must not leak into source/evidence.
    token_file = ROOT / ".tools/f20-private/credential.json"
    if token_file.is_file():
        record = json.loads(token_file.read_text())
        values.add(record["token"].encode())
        values.add(base64.b64encode((record["email"] + ":" + record["token"]).encode()))
    names = set(subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines())
    names.update(
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], text=True
        ).splitlines()
    )
    artifact_matches = 0
    for name in names:
        path = ROOT / name
        if path.is_file():
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            artifact_matches += any(secret in raw for secret in values)
    runtime_matches = 0
    token_shapes = 0
    scanned = []
    projects = [
        f"opspilot-full-test-f21-r{i}{suffix}" for i in range(1, 8) for suffix in ("", "-manager")
    ]
    for project in projects:
        ids = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project],
            text=True,
        ).split()
        for identifier in ids:
            # Exact project-label selection; no unrelated Full/MVP/other-project logs.
            raw = subprocess.check_output(["docker", "logs", identifier], stderr=subprocess.STDOUT)
            (PRIVATE / (identifier + ".log")).write_bytes(raw)
            runtime_matches += any(secret in raw.replace(b"\r\n", b"\n") for secret in values)
            token_shapes += len(
                re.findall(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}", raw)
            )
            scanned.append(identifier)
    report = {
        "artifact_files": len(names),
        "artifact_secret_matches": artifact_matches,
        "runtime_log_containers": len(scanned),
        "runtime_secret_matches": runtime_matches,
        "runtime_unredacted_jwt_shapes": token_shapes,
        "private_forensics": ".tools/f21-private-logs (ignored; never committed)",
        "child_stdio_captured": False,
        "scope_note": (
            "API/worker child stdout was discarded by the process harness; collector/application "
            "container logs, HTTP security tests and typed protected telemetry remain separate "
            "evidence. This is not a claim to have scanned discarded bytes."
        ),
        "passed": artifact_matches == runtime_matches == token_shapes == 0,
    }
    (EVIDENCE / "secret-scan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
