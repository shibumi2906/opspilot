"""Verify F16 adds scoped reviews without altering the protected ASVS baseline."""
import json
import subprocess
from pathlib import Path

BACKLOG = "docs/security/asvs-l2-requirement-backlog.json"
BASE = "a06d1a7"
baseline = json.loads(subprocess.check_output(["git", "show", BASE + ":" + BACKLOG]))
current = json.loads(Path(BACKLOG).read_text(encoding="utf-8-sig"))
assert current["requirements_count"] == len(current["requirements"]) == 253
assert len({r["id"] for r in current["requirements"]}) == 253
assert current["full_l2_status"] == baseline["full_l2_status"]
assert "NOT_MET" in str(current["full_l2_status"])
before = {r["id"]: r for r in baseline["requirements"]}
for row in current["requirements"]:
    inherited = {k: v for k, v in row.items() if not k.startswith("f16_")}
    assert inherited == before[row["id"]], row["id"]
assert {k: v for k, v in current.items() if k != "requirements"} == {
    k: v for k, v in baseline.items() if k != "requirements"
}
primary = [r for r in current["requirements"] if "f16_primary_review" in r]
assert len(primary) == 16
assert all(r["accountable_stage"] == "F16" for r in primary)
result = {
    "passed": True, "base": BASE, "requirements": 253,
    "all_inherited_fields_preserved": True,
    "scope_reviews": sum("f16_scope_review" in r for r in current["requirements"]),
    "primary_reviews": len(primary), "whole_requirement_closure": False,
    "full_l2_status": "NOT_MET",
}
out = Path("docs/full/evidence/f16/asvs-baseline-check.json")
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
