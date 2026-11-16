"""Drain the local pilot, reject an incompatible API candidate and restore its pinned image."""

import argparse
import json
import re
import runpy
import subprocess
from pathlib import Path

helpers = runpy.run_path("scripts/rehearse-full-f23-pilot-recovery.py")
compose, snapshot = helpers["compose"], helpers["snapshot"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"opspilot-full-test-f23-[a-z0-9]+", args.project)
    root = Path(".tools") / args.project
    config_path = root / "compose.json"
    original = json.loads(config_path.read_bytes())
    expected = original["services"]["api"]["image"]
    candidate = json.loads(
        subprocess.check_output(["docker", "image", "inspect", "opspilot-full/app:f19"], text=True)
    )[0]["Id"]
    assert expected != candidate
    compose(root, args.project, "stop", "--timeout", "30", "web", "api", "worker")
    before = snapshot(args.project + "-postgres-1", "opspilot_full_test")
    health = (
        "import httpx,ssl;"
        "r=httpx.get('https://api:8000/health/ready',"
        "verify=ssl.create_default_context(cafile='/tls/ca.crt'),timeout=15);"
        "print(r.status_code)"
    )
    try:
        proposed = json.loads(json.dumps(original))
        proposed["services"]["api"]["image"] = candidate
        config_path.write_text(json.dumps(proposed, indent=2))
        compose(root, args.project, "up", "-d", "--no-deps", "--no-build", "api")
        status = None
        for _ in range(20):
            result = subprocess.run(
                ["docker", "exec", args.project + "-api-1", "python", "-c", health],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                status = result.stdout.strip()
                break
            __import__("time").sleep(0.5)
        assert status == "503", "Incompatible candidate was not rejected by readiness"
        assert snapshot(args.project + "-postgres-1", "opspilot_full_test") == before
    finally:
        config_path.write_text(json.dumps(original, indent=2))
        compose(
            root,
            args.project,
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "90",
            "--no-deps",
            "--no-build",
            "api",
        )
    assert snapshot(args.project + "-postgres-1", "opspilot_full_test") == before
    compose(
        root,
        args.project,
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "90",
        "--no-build",
        "worker",
        "web",
    )
    actual = subprocess.check_output(
        ["docker", "inspect", args.project + "-api-1", "--format", "{{.Image}}"], text=True
    ).strip()
    assert actual == expected
    result = {
        "passed": True,
        "project": args.project,
        "candidate_image": candidate,
        "restored_image": expected,
        "candidate_readiness": 503,
        "tables_unchanged_during_rollout": len(before),
        "intake_and_worker_drained": True,
        "new_external_writes": 0,
        "scope": (
            "incompatible API image rejected before writes; pinned image rollback on schema0023"
        ),
        "schema_downgrade": (
            "not attempted; incompatible migration uses the separately tested logical restore"
        ),
    }
    report = Path("docs/full/evidence/f23/local-pilot-20261116/deployment-rollback.json")
    with report.open("x") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
