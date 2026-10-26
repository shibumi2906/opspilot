import json
from pathlib import Path


def test_full_transition_contract_is_closed_and_never_revives_terminal_run():
    contract = json.loads(Path("docs/full/state-transitions.json").read_text())
    tables = contract["transitions"]
    assert contract["schema_version"] == 1
    for table in tables.values():
        for source, targets in table.items():
            assert source not in targets
            assert len(targets) == len(set(targets))
            assert set(targets) <= table.keys()
    for terminal in ("completed", "cancelled", "failed"):
        assert tables["run"][terminal] == []
    assert "dispatch_started" not in tables["execution"]["unknown"]
    assert "approved" not in tables["approval"]["expired"]
    combinations = contract["action_combinations"]
    assert {row["execution"] for row in combinations} == tables["execution"].keys()
    for row in combinations:
        assert set(row["approvals"]) <= tables["approval"].keys()
        assert set(row["verifications"]) <= tables["verification"].keys()
        if "verified" in row["verifications"]:
            assert row["execution"] == "succeeded"
        if row["execution"] == "reserved":
            assert row["approvals"] == ["approved"]
