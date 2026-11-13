"""Explicit free-quota F22 launcher. Never prints or passes a key as a CLI argument."""

import argparse
import hashlib
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
    parser.add_argument("--diagnose-prior-failures", action="store_true")
    parser.add_argument("--probe-35k", action="store_true")
    parser.add_argument("--repeat-remaining-today", action="store_true")
    args = parser.parse_args()
    if not args.confirm_free_quota:
        parser.error("Confirm model/project eligibility and at least the requested unused quota")
    if args.diagnose_prior_failures and not args.continue_real_r1:
        parser.error("Diagnostic repeats require a verified continuation report")
    if args.probe_35k and (not args.continue_real_r1 or args.diagnose_prior_failures):
        parser.error("The 35k probe requires a completed schedule and its own diagnostic selection")
    if args.repeat_remaining_today and (
        args.report_name != "real-r7"
        or not args.continue_real_r1
        or args.probe_35k
        or args.diagnose_prior_failures
    ):
        parser.error("Remaining repeats require the real-r7 continuation of today's real-r6 probe")
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
    carried_tokens = 0
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
        prior_day = datetime.fromisoformat(prior["timestamp"]).date()
        if args.repeat_remaining_today:
            ledger_path = output.parent / previous_name / "token-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            entries = ledger["entries"]
            if (
                prior_day != today
                or ledger != prior["token_guard"]
                or ledger["limit"] != args.limit
                or ledger["unknown_usage"]
                or ledger["stop_reason"]
                or ledger["provider_attempts"] != len(entries)
                or any(entry["status"] != "known" for entry in entries)
                or [(r["id"], r["repeat"], r["passed"]) for r in prior["diagnostic_cases"]]
                != [("F18", 1, True), ("F22", 1, True)]
                or prior["cases"]
            ):
                raise ValueError("Today's prior quota use must be complete and reconciled")
            carried_tokens = sum(e["input_tokens"] + e["output_tokens"] for e in entries)
            if not 0 < carried_tokens == ledger["charged_or_reserved"] < args.limit:
                raise ValueError("Invalid carried token total")
            if prior["previous_report"] != "/reports/continuation/real-r5/real.json":
                raise ValueError("Unexpected canonical report")
            canonical = output.parent / "real-r5/real.json"
            if (
                hashlib.sha256(canonical.read_bytes()).hexdigest()
                != prior["previous_report_sha256"]
            ):
                raise ValueError("Canonical report hash mismatch")
        elif prior_day >= today:
            raise ValueError("A later quota day is required")
        if settings.openai_model != prior["requested_model"]:
            raise ValueError("Continuation requires the original model")
        previous = f"/reports/continuation/{previous_name}/real.json"
        if args.repeat_remaining_today:
            previous = prior["previous_report"]
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
        "-e",
        f"F22_CARRIED_TOKENS={carried_tokens}",
        "tests",
        "python",
        "-m",
        "tests.f22_lab",
        "--mode",
        "real",
        "--authorize-real",
        "--free-quota-confirmed",
        "--total-token-limit",
        str(args.limit - carried_tokens),
    ]
    if args.diagnose_prior_failures:
        command.append("--diagnose-prior-failures")
    if args.probe_35k:
        command.append("--probe-35k")
    if args.repeat_remaining_today:
        command.append("--repeat-remaining-today")
    # A different report name must not reset the owner's shared quota allowance.
    private.mkdir(exist_ok=True)
    with claim.open("x", encoding="utf-8") as target:
        json.dump(
            dict(
                limit=args.limit,
                carried_tokens=carried_tokens,
                segment_limit=args.limit - carried_tokens,
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
