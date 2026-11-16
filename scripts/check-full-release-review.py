"""Validate the separate 253-row release assessment without changing inherited ASVS records."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs/security/release-review-20261116"
BACKLOG = "docs/security/asvs-l2-requirement-backlog.json"
SOURCE_SHA256 = "8201b20eec2908c3380ac600c91c8ba746346fbb808859366abb232027532311"
DISPOSITIONS = {"supported_in_local_scope", "not_applicable_proposed", "verification_needed", "gap"}
SOURCE_REFS = {
    1: ["src/opspilot/api/routes_workspace.py", "web/src/WorkspaceViews.tsx"],
    2: ["src/opspilot/security/grants.py", "src/opspilot/agent/policy.py"],
    3: ["src/opspilot/auth/http.py", "infra/security/generate_local.py"],
    4: ["src/opspilot/security/http.py", "src/opspilot/api/main.py"],
    5: ["src/opspilot/api/routes_diagnostics.py", "scripts/full_backup.py"],
    6: ["infra/security/generate_local.py", "infra/identity/opspilot-realm.json"],
    7: ["src/opspilot/auth/store.py", "src/opspilot/auth/session_routes.py"],
    8: ["src/opspilot/tenancy/session.py", "src/opspilot/security/grants.py"],
    9: ["src/opspilot/auth/oidc.py", "src/opspilot/auth/service_context.py"],
    10: ["src/opspilot/auth/oidc.py", "infra/security/generate_local.py"],
    11: ["src/opspilot/security/keys.py", "scripts/full_backup.py"],
    12: ["src/opspilot/security/tls.py", "infra/security/generate_local.py"],
    13: ["infra/security/generate_local.py", "infra/full/Dockerfile"],
    14: ["src/opspilot/auth/store.py", "scripts/check-full-host.ps1"],
    15: ["uv.lock", "web/package-lock.json"],
    16: ["src/opspilot/logging.py", "src/opspilot/observability/collector.py"],
    17: ["OpsPilot_Full_Project_Specification.md", "web/package.json"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    baseline = json.loads(subprocess.check_output(["git", "show", "HEAD:" + BACKLOG], cwd=ROOT))
    inherited = json.loads((ROOT / BACKLOG).read_bytes())
    assert inherited == baseline, "Protected ASVS records changed"
    expected = {row["id"]: row for row in inherited["requirements"]}
    with (REVIEW / "requirements.tsv").open(encoding="utf-8", newline="") as handle:
        assessments = list(csv.DictReader(handle, delimiter="\t"))
    assert len(assessments) == len(expected) == 253
    assert {row["id"] for row in assessments} == set(expected)
    assert len({row["assessment"] for row in assessments}) == 253
    normative = ROOT / ".tools/host-review-20261116/asvs-5.0.0.flat.json"
    if normative.exists():
        raw = normative.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
        ids = {
            "v5.0.0-" + row["req_id"][1:]
            for row in json.loads(raw)["requirements"]
            if row["L"] in {"1", "2"}
        }
        assert ids == set(expected)
    proposals = [row for row in assessments if row["disposition"] == "not_applicable_proposed"]
    reviewed = set()
    owner_path = REVIEW / "owner-na-review.json"
    if owner_path.exists():
        owner = json.loads(owner_path.read_bytes())
        canonical = [{"id": row["id"], "assessment": row["assessment"]} for row in proposals]
        assert (
            owner["proposal_canonical_sha256"]
            == hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        ), "Owner applicability decision does not cover changed proposals"
        assert owner["decision"] == "accepted_applicability_only"
        assert owner["profile"] == "opspilot-full-test-f23-recovery4; scripted local pilot only"
        reviewed = set(owner["accepted_ids"])
        assert reviewed == {row["id"] for row in proposals}
        assert not owner["accepts_other_requirements"] and not owner["accepts_full_release_or_l2"]
    rows = []
    for assessment in assessments:
        assert assessment["disposition"] in DISPOSITIONS
        assert len(assessment["assessment"]) >= 40
        original = expected[assessment["id"]]
        contributions = []
        for name, value in original.items():
            if name.endswith("_primary_review"):
                contributions.append({"stage_review": name, **value})
        rows.append(
            {
                **assessment,
                "level": original["level"],
                "security_task": original["security_task"],
                "accountable_stage": original["accountable_stage"],
                "inherited_requirement_ref": BACKLOG + "#" + assessment["id"],
                "existing_primary_contributions": contributions,
                "source_review_refs": SOURCE_REFS[
                    int(assessment["id"].split("-")[1].split(".")[0])
                ],
                "closure": "OPEN: scoped support is not a full-norm pass; "
                "N/A requires owner review",
            }
        )
        if assessment["id"] in reviewed:
            rows[-1].update(
                disposition="not_applicable_owner_reviewed",
                owner_review_ref="docs/security/release-review-20261116/owner-na-review.json",
                closure="N/A owner-reviewed only for the exact scripted local pilot scope; "
                "reassess if functionality or deployment changes",
            )
    assert all((ROOT / ref).is_file() for refs in SOURCE_REFS.values() for ref in refs)
    result = {
        "review_date": "2026-11-16",
        "profile": "opspilot-full-test-f23-recovery4; scripted local pilot; main Full remains 0019",
        "normative_source": "https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release",
        "normative_sha256": SOURCE_SHA256,
        "normative_license": "CC-BY-SA-4.0; normative text is not reproduced",
        "inherited_backlog_canonical_sha256": hashlib.sha256(
            json.dumps(inherited, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "inherited_records_unchanged": 253,
        "rows": len(rows),
        "dispositions": dict(Counter(row["disposition"] for row in rows)),
        "full_norms_closed": 0,
        "owner_na_approvals": len(reviewed),
        "applicable_requirements": 253 - len(reviewed),
        "full_asvs_l2": "NOT_MET",
        "requirements": rows,
    }
    path = REVIEW / "review.json"
    proposal_text = (
        "# Proposed non-applicable requirements\n\n"
        "Scope: scripted local recovery4 pilot only. "
        + (
            "Owner confirmed all43 in [owner review](owner-na-review.json). "
            if reviewed
            else "These43 proposals require owner applicability review. "
        )
        + "This is not an acceptance of the other210 requirements "
        "or a whole ASVS L2 pass. Existing protected backlog fields remain unchanged.\n\n"
        "| ID | Rationale |\n|---|---|\n"
        + "".join("| " + row["id"] + " | " + row["assessment"] + " |\n" for row in proposals)
    )
    if args.write:
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (REVIEW / "not-applicable-proposals.md").write_text(proposal_text, encoding="utf-8")
    else:
        assert json.loads(path.read_bytes()) == result, (
            "Regenerate review.json after changing assessments"
        )
    print(json.dumps({k: v for k, v in result.items() if k != "requirements"}))
    if not args.write:
        assert (REVIEW / "not-applicable-proposals.md").read_text(encoding="utf-8") == proposal_text


if __name__ == "__main__":
    main()
