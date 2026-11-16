import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from opspilot.integrations.jira_payload import SandboxMapping, comment_payload, issue_payload
from opspilot.integrations.jira_simulator_receipts import (
    Observation,
    SimulatedOperation,
    SimulatorReceipts,
)
from opspilot.integrations.jira_verification import Outcome

MAPPING = SandboxMapping("https://synthetic.atlassian.net", "1", "2", 1)


def test_lost_response_and_concurrent_replay(tmp_path):
    operation_id = uuid4()
    payload = issue_payload(MAPPING, operation_id, summary="Synthetic", description="Example")
    operation = SimulatedOperation(uuid4(), operation_id, MAPPING, payload)
    path = tmp_path / "receipts.db"
    receipts = SimulatorReceipts(path)
    provider = []

    def post():
        fields = json.loads(payload)["fields"]
        provider.append(
            Observation(MAPPING.site, "1", "45", {"id": "45", "fields": fields}, str(operation_id))
        )
        raise TimeoutError

    def dispatch(_):
        return receipts.dispatch(operation, operation.digest(), post)

    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(dispatch, range(12))) == [Outcome.UNKNOWN] * 12
    assert len(provider) == 1
    restarted = SimulatorReceipts(path)
    assert restarted.reconcile(operation, [], complete=True) == Outcome.UNKNOWN
    assert restarted.reconcile(operation, provider, complete=False) == Outcome.UNKNOWN
    assert restarted.reconcile(operation, provider, complete=True) == Outcome.VERIFIED
    assert restarted.dispatch(operation, operation.digest(), post) == Outcome.VERIFIED
    assert len(provider) == 1


@pytest.mark.parametrize("scenario", ["wrong_issue", "duplicate", "wrong_site", "correct"])
def test_comment_reconciliation_scope(tmp_path, scenario):
    marker = uuid4()
    payload = comment_payload(marker, body="Synthetic comment")
    operation = SimulatedOperation(uuid4(), marker, MAPPING, payload, "45")
    receipts = SimulatorReceipts(tmp_path / "receipts.db")
    observed = Observation(
        "https://other.atlassian.net" if scenario == "wrong_site" else MAPPING.site,
        "1",
        "46" if scenario == "wrong_issue" else "45",
        {"id": "3", "body": json.loads(payload)["body"]},
        {"operation_id": str(marker)},
    )
    with pytest.raises(ValueError, match="No matching dispatch receipt"):
        receipts.reconcile(operation, [observed], complete=True)
    receipts.dispatch(operation, operation.digest(), lambda: None)
    observed_rows = [observed, observed] if scenario == "duplicate" else [observed]
    expected = Outcome.VERIFIED if scenario == "correct" else Outcome.NEEDS_ATTENTION
    assert receipts.reconcile(operation, observed_rows, complete=True) == expected


def test_crash_after_receipt_commit_never_redispatches(tmp_path):
    marker = uuid4()
    operation = SimulatedOperation(
        uuid4(),
        marker,
        MAPPING,
        issue_payload(MAPPING, marker, summary="Example", description="x"),
    )
    path = tmp_path / "receipts.db"

    def crash():
        raise SystemExit

    receipts = SimulatorReceipts(path)
    with pytest.raises(ValueError, match="Approval differs"):
        receipts.dispatch(operation, "wrong", crash)
    with pytest.raises(SystemExit):
        receipts.dispatch(operation, operation.digest(), crash)
    assert SimulatorReceipts(path).dispatch(operation, operation.digest(), crash) == Outcome.UNKNOWN


def test_late_duplicate_escalates_previously_verified_operation(tmp_path):
    marker = uuid4()
    payload = issue_payload(MAPPING, marker, summary="Example", description="x")
    operation = SimulatedOperation(uuid4(), marker, MAPPING, payload)
    path = tmp_path / "receipts.db"
    receipts = SimulatorReceipts(path)
    receipts.dispatch(operation, operation.digest(), lambda: None)
    observation = Observation(
        MAPPING.site, "1", "45", {"id": "45", "fields": json.loads(payload)["fields"]}, str(marker)
    )
    assert receipts.reconcile(operation, [observation], complete=True) == Outcome.VERIFIED
    assert receipts.reconcile(operation, [], complete=False) == Outcome.VERIFIED
    restarted = SimulatorReceipts(path)
    assert (
        restarted.reconcile(operation, [observation, observation], complete=True)
        == Outcome.NEEDS_ATTENTION
    )

    def unexpected_write():
        pytest.fail("A late duplicate must never authorize another dispatch")

    assert (
        restarted.dispatch(operation, operation.digest(), unexpected_write)
        == Outcome.NEEDS_ATTENTION
    )
    assert restarted.reconcile(operation, [observation], complete=True) == Outcome.NEEDS_ATTENTION
