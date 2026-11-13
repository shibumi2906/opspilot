"""Check F23 artifacts and retained rehearsal logs without exporting private values."""

import argparse
import json
import re
import subprocess
from pathlib import Path

BACKLOG = "docs/security/asvs-l2-requirement-backlog.json"
REPORTS = Path("docs/full/evidence/f23")


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    args = parser.parse_args()
    assert re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", args.project)
    private = Path(".tools/f23") / args.project
    before = json.loads(command("git", "show", "d17b486:" + BACKLOG))
    current = json.loads(Path(BACKLOG).read_text(encoding="utf-8"))
    assert current == before and len({row["id"] for row in current["requirements"]}) == 253
    values = {
        line.partition("=")[2].encode() for line in (private / "lab.env").read_text().splitlines()
    }
    for path in private.rglob("*"):
        if path.is_file() and path.suffix in {".key", ".token", ".pem"}:
            values.update(path.read_bytes().splitlines())
    initialization = json.loads((private / "manager-recovery/initialization.json").read_bytes())
    values.update(
        value.encode()
        for value in [
            initialization["root_token"],
            *initialization["keys"],
            *initialization["keys_base64"],
        ]
    )
    values = {value for value in values if len(value) >= 20 and not value.startswith(b"---")}

    def contains_secret(raw):
        return any(value in raw for value in values)

    files = set(command("git", "diff", "d17b486", "--name-only").decode().splitlines())
    files.update(command("git", "ls-files", "--others", "--exclude-standard").decode().splitlines())
    artifacts = sum(
        contains_secret(Path(path).read_bytes()) for path in files if Path(path).is_file()
    )
    logs = [(private / "rehearsal.log").read_bytes()]
    for project in (args.project, args.project + "-restore", args.project + "-manager"):
        selected = (
            command(
                "docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"
            )
            .decode()
            .split()
        )
        logs.extend(command("docker", "logs", container) for container in selected)
    matches = sum(contains_secret(raw) for raw in logs)
    jwt_shapes = sum(
        len(re.findall(rb"eyJ[\w-]{12,}\.[\w-]{12,}\.[\w-]{12,}", raw)) for raw in logs
    )
    result = {
        "project": args.project,
        "protected_asvs_records_unchanged": 253,
        "candidate_files_checked": len(files),
        "log_streams_checked": len(logs),
        "artifact_secret_matches": artifacts,
        "log_secret_matches": matches,
        "log_jwt_shapes": jwt_shapes,
        "fresh_target_image_os_scan": "NOT_RUN",
        "full_asvs_l2": "NOT_MET",
    }
    (REPORTS / "security.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    assert artifacts == matches == jwt_shapes == 0


if __name__ == "__main__":
    main()
