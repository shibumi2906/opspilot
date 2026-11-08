"""Record measured F22 gates without promoting local evidence to release acceptance."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path.cwd()
OUT = ROOT / "docs/full/evidence/f22"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8-sig"))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    report = read("scripted.json")
    regression = read("mvp-regression/scripted.json")
    security = read("security/checks.json")
    backlog = Path("docs/security/asvs-l2-requirement-backlog.json")
    baseline = subprocess.check_output(["git", "show", "e1674e6:" + backlog.as_posix()])
    current = backlog.read_bytes().replace(b"\r\n", b"\n")
    assert baseline.replace(b"\r\n", b"\n") == current
    asvs = dict(
        rows=len(json.loads(current)["requirements"]),
        entire_backlog_unchanged=True,
        sha256=digest(current),
        sec_scope=["SEC-01", "SEC-10", "SEC-11"],
        whole_l2="NOT_MET",
    )
    assert asvs["rows"] == 253
    write("asvs-baseline.json", asvs)
    # Preserve the separate MVP corpus and its implementation exactly.
    protected = ["scenarios.yaml", "runner.py", "schema.py", "assertions.py", "report.py"]
    for name in protected:
        path = "src/opspilot/evals/" + name
        original = subprocess.check_output(["git", "show", "e1674e6:" + path])
        assert original.replace(b"\r\n", b"\n") == Path(path).read_bytes().replace(b"\r\n", b"\n")
    # Human review is a queue, never an automatic pass based on canonical predicates.
    review = [
        dict(
            id=r["id"],
            split=r["split"],
            run_id=r.get("run_id"),
            facts=(r.get("report") or {}).get("facts", []),
            hypotheses=(r.get("report") or {}).get("hypotheses", []),
            judgment=None,
            reviewer=None,
        )
        for r in report["cases"]
    ]
    write(
        "human-review.json",
        dict(
            status="pending",
            rows=review,
            note="Canonical scripted predicates do not replace human review",
        ),
    )
    write(
        "real-holdout.json",
        dict(
            status="blocked",
            planned_distinct=50,
            dev_runs=30,
            holdout_runs=60,
            planned_runs=90,
            recorded_runs=0,
            setup_errors=0,
            setup_attempted=False,
            model=None,
            prompt_sha256=report["prompt_sha256"],
            actual_spend_usd=0,
            provider_calls=0,
            unknown_usage_count=0,
            holdout_unseen=False,
            exposure="Public corpus inspected during implementation, no prompt tuning performed",
            reason="Owner forbids paid calls; real execution not authorized",
            human_review="pending",
            remote_ci="not_run",
        ),
    )
    unit = ElementTree.parse(OUT / "unit.xml").getroot()
    suites = list(unit.iter("testsuite"))
    counts = {
        k: sum(int(s.attrib.get(k, "0")) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    mixed = ElementTree.parse(OUT / "mixed-regression.xml").getroot()
    mixed_counts = {
        k: sum(int(s.attrib.get(k, "0")) for s in mixed.iter("testsuite"))
        for k in ("tests", "failures", "errors", "skipped")
    }
    checks = dict(
        stage="F22",
        base="e1674e6",
        recorded_at=datetime.now(UTC).isoformat(),
        stage_status="blocked",
        local_scripted=report["summary"],
        mvp_regression=regression["summary"],
        unit=counts,
        mixed_regression=mixed_counts,
        security=security,
        secret_scan=read("secret-scan.json"),
        asvs=asvs,
        config=read("config-gates.json"),
        static=read("static-checks.json"),
        source_verification=read("source-verification.json"),
        mvp_after=read("mvp-after.json"),
        cleanup=read("cleanup.json"),
        full_pilot="NOT_MET",
        whole_asvs_l2="NOT_MET",
        f20="blocked; real Jira deferred; write/one-attempt/reconciliation incomplete",
        f21="blocked; functional gates passed; manager HIGH remains",
        real="blocked",
        human_review="pending",
        remote_ci="not_run",
        main_full="F18/schema0019; no build/migration/seed/restart",
        paid_calls=0,
        vendor_calls=0,
        remote_ci_runs=0,
        push=0,
        limitations=[
            "ASGI BFF HTTP with in-process worker claims; native MCP TCP, "
            "real PostgreSQL/Redis/manager",
            "Fixture sessions are not a real IdP login acceptance",
            "50 cases use single-ticket v1 actions; mixed-plan regressions are separate",
            "Holdout public and inspected; no unseen quality claim",
            "Security gate NOT_MET; manager CVE-2026-78661 has no exception",
            "No live Jira or F20 dispatch/reconciliation evidence",
            "CI workflow prepared; no remote execution evidence",
        ],
    )
    write("checks.json", checks)
    print(
        json.dumps(
            dict(
                stage=checks["stage_status"],
                scripted=report["summary"]["passed"],
                mvp=regression["summary"]["passed"],
                units=counts,
            )
        )
    )


if __name__ == "__main__":
    main()
