"""Check portfolio packaging, screenshot provenance and the dated evidence it cites."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_bytes())


def main():
    scope = read("docs/full/portfolio-status.json")
    assert scope["status"] == "complete"
    assert scope["acceptance_scope"] == "engineering portfolio and local synthetic demonstrator"
    assert scope["production_release_accepted"] is False
    assert scope["asvs_l2_compliance_claimed"] is False
    assert scope["mvp_in_scope"] is False and scope["mvp_files_edited"] is False
    assert scope["new_jira_dispatches"] == scope["paid_provider_calls"] == 0

    capture = read(scope["capture_ref"])
    assert capture["synthetic"] and capture["actual_application_ui"]
    assert capture["model"] == "scripted" and capture["verification"] == "verified"
    assert capture["operator_approval_denied"] and capture["approver_approval_enabled"]
    assert set(capture["screenshot_sha256"]) == {
        "workspace.png",
        "approval.png",
        "verified.png",
        "history.png",
    }
    for name, expected in capture["screenshot_sha256"].items():
        path = ROOT / "docs/assets/full" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name

    video = read(scope["english_demo_ref"])
    assert video["actual_application_ui"] and video["synthetic"]
    assert video["model"] == "scripted" and not video["authentication_recorded"]
    assert video["paid_calls"] == video["external_tts_requests"] == video["jira_dispatches"] == 0
    assert video["approved_local_tickets"] == video["rejected_runs_without_ticket"] == 1
    assert video["same_saved_action_verified"] and video["duration_seconds"] == 180
    assert (video["width"], video["height"], video["language"]) == (1920, 1080, "en")
    assert len(video["chapters"]) == 11
    assert set(video["sha256"]) == {
        "opspilot-full-demo-en.mp4",
        "opspilot-full-demo-en.srt",
        "demo-en-script.json",
    }
    for name, expected in video["sha256"].items():
        path = ROOT / "docs/assets/full" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name

    ci = read(scope["verified_baseline_ci_ref"])
    assert ci["head"] == "79a856b8227498cc2a1b311bd832bdb34559beca"
    assert ci["ci_status"] == "SUCCESS" and ci["pushed"]
    assert ci["full_scripted"] == {"passed": 50, "total": 50}
    assert ci["mvp_scripted"] == {"passed": 12, "total": 12}
    assert ci["junit"]["jira-runtime"]["tests"] == 45
    assert ci["junit"]["backup-unit"]["tests"] == 9
    assert ci["security_gate"]["passed"] and not ci["security_gate"]["blocking"]
    assert ci["secret_gate"]["passed"] and ci["source_hashes_verified"] == 144

    regression = ROOT / "docs/full/evidence/f20/backend-regression-20261116T063232858.xml"
    suites = ET.parse(regression).getroot().iter("testsuite")
    totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, "0"))
    assert totals == {"tests": 674, "failures": 0, "errors": 0, "skipped": 71}

    files = [
        "README.md",
        "START-HERE.md",
        "CURRENT-HANDOFF.md",
        "docs/full/architecture.md",
        "docs/full/portfolio-completion.md",
        "docs/full/showcase-tour.md",
        "docs/full/demo-video.md",
    ]
    links = 0
    for relative in files:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8-sig")
        targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
        targets += re.findall(r'(?:src|href)="([^"]+)"', text)
        for target in targets:
            target = unquote(target.split("#", 1)[0].strip("<>"))
            if not target or re.match(r"(?:https?|mailto|codex):", target):
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_relative_to(ROOT), (relative, target)
            assert resolved.exists(), (relative, target)
            links += 1

    print(
        json.dumps(
            {
                "passed": True,
                "portfolio": "complete",
                "screenshots_verified": 4,
                "english_demo_seconds": video["duration_seconds"],
                "local_document_links": links,
                "baseline_full_scripted": "50/50",
                "baseline_backend": "603 passed / 71 dedicated-profile skips",
                "production_asvs_claim": False,
            }
        )
    )


if __name__ == "__main__":
    main()
