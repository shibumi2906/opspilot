"""Explicit free-quota F22 launcher. Never prints or passes a key as a CLI argument."""

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from opspilot.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-free-quota", action="store_true")
    parser.add_argument("--project", default="opspilot-full-test-f22-r1")
    parser.add_argument("--subnet", type=int, default=34)
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--report-name", required=True)
    parser.add_argument("--continue-real-r1", action="store_true")
    args = parser.parse_args()
    if not args.confirm_free_quota:
        parser.error("Confirm model/project eligibility and at least the requested unused quota")
    if not re.fullmatch(r"opspilot-full-test-f22-[a-z0-9-]+", args.project):
        parser.error("F22-only project required")
    if not re.fullmatch(r"[a-z0-9-]+", args.report_name):
        parser.error("Simple report name required")
    if not 34 <= args.subnet <= 99 or not 0 < args.limit <= 200000:
        parser.error("Invalid subnet or owner token limit")
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    if branch != "codex/opspilot-full":
        raise ValueError("Full branch required")
    settings = Settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise ValueError("Full .env lacks a local provider key or explicit model")
    if settings.llm_mode != "scripted":
        raise ValueError("Keep normal Full LLM_MODE=scripted; real mode is command scoped")
    output = Path("docs/full/evidence/f22/continuation") / args.report_name
    if output.exists():
        raise ValueError("Existing report cannot receive another fresh budget")
    log = Path(".tools") / ("f22-real-" + args.report_name + ".log")
    if log.exists():
        raise ValueError("Existing log cannot receive another fresh budget")
    private = Path(".tools/f22-real")
    claim = private / "quota-authorization.json"
    previous = ""
    if args.continue_real_r1:
        match = re.fullmatch(r"real-r([1-9][0-9]*)", args.report_name)
        if not match or int(match[1]) < 2 or not claim.is_file():
            raise ValueError("Continuation requires the original claim and numbered report")
        segment = int(match[1])
        previous_name = f"real-r{segment - 1}"
        if segment > 2 and not (private / f"quota-authorization-{previous_name}.json").is_file():
            raise ValueError("Missing prior quota claim")
        prior = json.loads(
            (output.parent / previous_name / "real.json").read_text(encoding="utf-8")
        )
        today = datetime.now(UTC).date()
        if datetime.fromisoformat(prior["timestamp"]).date() >= today:
            raise ValueError("A later quota day is required")
        if settings.openai_model != prior["requested_model"]:
            raise ValueError("Continuation requires the original model")
        previous = f"/reports/continuation/{previous_name}/real.json"
        claim = private / f"quota-authorization-{args.report_name}.json"
    # Only the provider key is injected from the local settings, never MVP credentials.
    env = {
        **os.environ,
        "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
        "OPENAI_MODEL": settings.openai_model,
        "OPENAI_REASONING_EFFORT": settings.openai_reasoning_effort,
        "F22_SUBNET_PREFIX": "10.245." + str(args.subnet),
        "F22_MANAGER_DIR": "./.tools/f22/" + args.project + "/manager",
    }
    command = ["docker", "compose", "--env-file", ".env", "-p", args.project]
    for file in (
        "compose.full.yaml",
        "compose.full.test.yaml",
        "compose.full.f13-checks.yaml",
        "compose.full.f16-checks.yaml",
        "compose.full.f17-checks.yaml",
        "compose.full.f22-checks.yaml",
    ):
        command += ["-f", file]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    command += [
        "run",
        "--rm",
        "--no-deps",
        "-e",
        "OPENAI_API_KEY",
        "-e",
        "OPENAI_MODEL",
        "-e",
        "OPENAI_REASONING_EFFORT",
        "-e",
        "F22_COMMIT=" + commit,
        "-e",
        "F22_REPORT_DIR=/reports/continuation/" + args.report_name,
        "-e",
        "F22_PREVIOUS_REPORT=" + previous,
        "tests",
        "python",
        "-m",
        "tests.f22_lab",
        "--mode",
        "real",
        "--authorize-real",
        "--free-quota-confirmed",
        "--total-token-limit",
        str(args.limit),
    ]
    # A different report name must not reset the owner's shared quota allowance.
    private.mkdir(exist_ok=True)
    with claim.open("x", encoding="utf-8") as target:
        json.dump(
            dict(
                limit=args.limit,
                model=settings.openai_model,
                report=args.report_name,
                status="reserved_before_launch",
                previous_report=previous or None,
            ),
            target,
        )
        target.flush()
        os.fsync(target.fileno())
    # No automatic reset on launch failure: network/usage may be ambiguous.
    with log.open("xb") as target:
        return subprocess.run(command, env=env, stdout=target, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
