"""Preserve every inherited ASVS field; only F18 contributions may be added."""

import json
import subprocess
from pathlib import Path

path = "docs/security/asvs-l2-requirement-backlog.json"
base = json.loads(
    subprocess.check_output(["git", "show", "017b68bb34e85e95013076d570bd14b5519f842b:" + path])
)
current = json.loads(Path(path).read_text(encoding="utf-8"))
assert len(current["requirements"]) == current["requirements_count"] == 253
before = {r["id"]: r for r in base["requirements"]}
assert len(before) == len({r["id"] for r in current["requirements"]}) == 253
for row in current["requirements"]:
    assert {k: v for k, v in row.items() if not k.startswith("f18_")} == before[row["id"]], row[
        "id"
    ]
assert {k: v for k, v in current.items() if k != "requirements"} == {
    k: v for k, v in base.items() if k != "requirements"
}
result = {
    "passed": True,
    "base": "017b68bb34e85e95013076d570bd14b5519f842b",
    "protected_requirements": 253,
    "inherited_fields_preserved": True,
    "whole_requirement_closure": False,
    "full_L2": "NOT_MET",
    "scope_reviews": sum("f18_scope_review" in r for r in current["requirements"]),
    "primary_reviews": sum("f18_primary_review" in r for r in current["requirements"]),
}
Path("docs/full/evidence/f18/asvs-baseline-check.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))
