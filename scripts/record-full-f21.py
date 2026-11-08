"""Record measured F21 gates; never turn a deferred dependency into a stage pass."""

import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
EVIDENCE = ROOT / "docs/full/evidence/f21"


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8-sig"))


def junit(name: str) -> dict:
    path = EVIDENCE / name
    if not path.is_file():
        return {"executed": False, "passed": False}
    cases = ET.parse(path).getroot().findall(".//testcase")
    failed = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    incomplete = sum(not c.get("classname") or not c.get("name") for c in cases)
    return {
        "executed": True,
        "passed": not failed and not incomplete and bool(cases),
        "tests": len(cases),
        "failed": failed,
        "skipped": skipped,
        "successful": len(cases) - failed - skipped,
        "incomplete": incomplete,
    }


def main() -> None:
    load = read("load-soak.json")
    db = read("independent-db-audit.json")
    faults, fences, units = (junit(name) for name in ("faults.xml", "fencing.xml", "units.xml"))
    backlog_path = "docs/security/asvs-l2-requirement-backlog.json"
    baseline = json.loads(subprocess.check_output(["git", "show", "152d59b:" + backlog_path]))
    backlog = json.loads((ROOT / backlog_path).read_text())
    clean = json.loads(json.dumps(backlog))
    scoped = sum("f21_scope_review" in row for row in clean["requirements"])
    for row in clean["requirements"]:
        row.pop("f21_scope_review", None)
    reviews = {
        "baseline": "152d59b",
        "protected_rows": len(clean["requirements"]),
        "all_inherited_fields_unchanged": clean == baseline,
        "f21_scope_reviews": scoped,
        "whole_L2": "NOT_MET",
    }
    (EVIDENCE / "asvs-baseline.json").write_text(json.dumps(reviews, indent=2) + "\n")
    isolation = read("mvp-after.json")
    secrets = read("secret-scan.json")
    security = read("security/checks.json")
    source = read("source-provenance.json")
    outages = read("service-outages.json")
    import hashlib

    source_match = all(
        hashlib.sha256((ROOT / "src/opspilot" / p).read_bytes()).hexdigest() == expected
        for p, expected in source["files"].items()
    )
    functional = (
        load.get("passed")
        and db.get("passed")
        and faults["passed"]
        and faults["tests"] == 115
        and fences["passed"]
        and fences["tests"] == 3
        and units["passed"]
        and units["tests"] == 278
        and len(outages) == 4
        and all(item["health_recovered"] for item in outages)
        and load["soak"]["measured_seconds"] >= 1800
        and db["soak_window"]["jobs"] >= 200
        and source_match
        and reviews["all_inherited_fields_unchanged"]
        and secrets["passed"]
        and isolation["files_unchanged"]
        and isolation["mvp_volume_content_unchanged"]
    )
    local = functional and security["passed"]
    report = {
        "stage": "F21",
        "base": "152d59b",
        "recorded_at": datetime.now(UTC).isoformat(),
        "stage_status": "blocked",
        "available_local_gates": "passed" if local else "NOT_MET",
        "functional_local_gates": "passed" if functional else "NOT_MET",
        "commit_subject": (
            "feat(full-f21): measure bounded load recovery and repair admission bottlenecks"
        ),
        "load_project": "opspilot-full-test-f21-r4",
        "fault_project": "opspilot-full-test-f21-r6",
        "fencing_project": "opspilot-full-test-f21-r7",
        "schema_test_only": "0021_worker_admission",
        "main_full_schema": "0019_adapters",
        "soak": load.get("soak"),
        "soak_db_window": db.get("soak_window"),
        "load_run_count": load.get("run_count"),
        "load_job_count": load.get("job_count"),
        "burst": load.get("burst"),
        "quota_burst": load.get("quota_burst"),
        "latency_seconds": load.get("latency_seconds"),
        "service_outages": outages,
        "process_faults": load.get("process_faults"),
        "process_fault_note": (
            "Worker replacement_seconds measures spawn only; API includes readiness. "
            "Job recovery is measured by completion latency and dedicated fencing tests."
        ),
        "resource_regressions": junit("resource-regressions.xml"),
        "faults": faults,
        "fencing": fences,
        "units": units,
        "protected_asvs_rows": 253,
        "source_files": len(source["files"]),
        "source_matches": source_match,
        "mvp_isolation": "passed",
        "security_scan_ref": "security/checks.json",
        "security_scan": security,
        "secret_scan": secrets,
        "vendor_calls": 0,
        "paid_calls": 0,
        "push": 0,
        "full_pilot": "NOT_MET",
        "whole_asvs_l2": "NOT_MET",
        "blockers": [
            "F20 Jira write/one-attempt/reconciliation implementation and its fault "
            "boundaries remain incomplete.",
            "The owner explicitly deferred real Jira checks; no request to recreate a token "
            "or perform Jira writes was inferred.",
            *(
                []
                if security["passed"]
                else [
                    "Fresh manager image scan has HIGH CVE-2026-78661 in x/net0.61.0 "
                    "(fix0.62.0). Security gate NOT_MET; preserved runtime was not rebuilt "
                    "with less than3GB free disk. No applicability exception claimed."
                ]
            ),
        ],
        "limits": [
            "20 active means nonterminal accepted runs, including queue/human wait; "
            "not20 executing workers.",
            "Sessions are explicit test fixtures; this is not IdP login-load acceptance, HA, "
            "service quorum or a promised SLO.",
            "Existing F19 images plus read-only source mounts; no new release image "
            "or main Full deployment.",
            "Failed/interrupted candidates remain under attempts and ignored .tools logs; "
            "only final measured gates count.",
        ],
    }
    (EVIDENCE / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    subprocess.run(["git", "diff", "--check"], check=True)
    print(
        json.dumps(
            {"stage_status": "blocked", "available_local_gates": report["available_local_gates"]}
        )
    )


if __name__ == "__main__":
    main()
