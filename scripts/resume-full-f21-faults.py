"""Resume completed assertions from an interrupted pytest run; require exact collection coverage."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.cwd()))
REPORT = Path("/reports")
prior = ET.parse(REPORT / "attempts/faults-r2-interrupted.xml").getroot()
completed = [
    c
    for c in prior.findall(".//testcase")
    if c.get("classname")
    and c.get("name")
    and not any(c.find(tag) is not None for tag in ("failure", "error"))
]
ids = {c.get("classname").replace(".", "/") + ".py::" + c.get("name") for c in completed}
assert len(ids) == len(completed) == 52
files = [
    "f21_resilience",
    "durable_jobs",
    "freshness",
    "action_grants",
    "authorization",
    "human_commands",
    "governance",
    "recovery",
    "checkpoint_compatibility",
    "lifecycle_serialization",
    "security_baseline",
    "sse",
    "observability",
]


class Coverage:
    all_ids: set[str]

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, items):
        self.all_ids = {item.nodeid for item in items}
        assert ids <= self.all_ids, "Prior assertions do not match current collection"


coverage = Coverage()
result = pytest.main(
    [
        "-p",
        "no:cacheprovider",
        "-vv",
        "-o",
        "faulthandler_timeout=120",
        *(f"tests/integration/test_{f}.py" for f in files),
        *(f"--deselect={node}" for node in sorted(ids)),
        "--junitxml=/reports/faults-remainder.xml",
    ],
    plugins=[coverage],
)
if result != 0:
    raise SystemExit(result)
remainder = ET.parse(REPORT / "faults-remainder.xml").getroot().findall(".//testcase")
assert all(c.get("classname") and c.get("name") for c in remainder)
assert len(completed) + len(remainder) == len(coverage.all_ids)
assert len({(c.get("classname"), c.get("name")) for c in completed + remainder}) == len(
    coverage.all_ids
)
suite = ET.Element(
    "testsuite", name="F21 exact collection, split execution", tests=str(len(coverage.all_ids))
)
for case in completed + remainder:
    suite.append(case)
suite.set("failures", str(sum(c.find("failure") is not None for c in suite)))
suite.set("errors", str(sum(c.find("error") is not None for c in suite)))
suite.set("skipped", str(sum(c.find("skipped") is not None for c in suite)))
suite.set("time", str(sum(float(c.get("time", "0")) for c in suite)))
root = ET.Element("testsuites")
root.append(suite)
ET.ElementTree(root).write(REPORT / "faults.xml", encoding="utf-8", xml_declaration=True)
print(
    f"Exact coverage: {len(completed)} prior assertions + {len(remainder)} remainder "
    f"= {len(coverage.all_ids)}",
    flush=True,
)
