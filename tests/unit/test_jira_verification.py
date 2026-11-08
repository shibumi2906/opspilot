import copy
import json
from uuid import UUID

import pytest

from opspilot.integrations.jira_payload import SandboxMapping, comment_payload, issue_payload
from opspilot.integrations.jira_verification import (
    Outcome,
    comment_matches,
    issue_matches,
    normalize_adf,
    reconciliation,
)

OP = UUID(int=1)
MAPPING = SandboxMapping("https://example.atlassian.net", "10000", "10001", 1)


def test_issue_verification_binds_destination_business_fields_and_operation():
    outbound = issue_payload(MAPPING, OP, summary="Incident", description="Literal **text**\nnext")
    observed = {"id": "10002", "fields": json.loads(outbound)["fields"]}
    assert issue_matches(MAPPING, outbound, observed, property_value=str(OP), operation_id=OP)
    assert not issue_matches(
        MAPPING, outbound, observed, property_value=str(UUID(int=2)), operation_id=OP
    )
    for key, value in (
        ("project", {"id": "20000"}),
        ("issuetype", {"id": "20001"}),
        ("summary", "Changed"),
        ("description", None),
    ):
        changed = copy.deepcopy(observed)
        changed["fields"][key] = value
        assert not issue_matches(
            MAPPING, outbound, changed, property_value=str(OP), operation_id=OP
        )


def test_adf_normalization_is_narrow_and_preserves_marks_and_unknown_attributes():
    outbound = comment_payload(OP, body="exact")
    observed = {"id": "10003", "body": json.loads(outbound)["body"]}
    observed["body"]["content"][0]["attrs"] = {"localId": "vendor-assigned"}
    assert comment_matches(outbound, observed, property_value=str(OP), operation_id=OP)
    observed["body"]["content"][0]["attrs"]["other"] = "unexpected"
    assert not comment_matches(outbound, observed, property_value=str(OP), operation_id=OP)
    observed["body"]["content"][0].pop("attrs")
    observed["body"]["content"][0]["content"][0]["marks"] = [{"type": "strong"}]
    assert not comment_matches(outbound, observed, property_value=str(OP), operation_id=OP)


def test_text_and_markers_are_literal_and_exact():
    outbound = comment_payload(OP, body="[x](https://evil.test)\r\nline")
    assert outbound == comment_payload(OP, body="[x](https://evil.test)\nline")
    document = json.loads(outbound)
    assert document["body"]["content"][0]["content"][0]["text"] == "[x](https://evil.test)"
    assert normalize_adf(document) == document
    assert not comment_matches(
        outbound, {"id": "10003", "body": document["body"]}, property_value=None, operation_id=OP
    )


def test_prepared_marker_cannot_be_rebound_to_another_operation():
    outbound = comment_payload(OP, body="exact")
    observed = {"id": "10003", "body": json.loads(outbound)["body"]}
    other = UUID(int=2)
    assert not comment_matches(outbound, observed, property_value=str(other), operation_id=other)
    outbound_issue = issue_payload(MAPPING, OP, summary="Incident", description="exact")
    issue = {"id": "10002", "fields": json.loads(outbound_issue)["fields"]}
    assert not issue_matches(
        MAPPING, outbound_issue, issue, property_value=str(other), operation_id=other
    )


@pytest.mark.parametrize(
    "matches,complete,outcome",
    [
        ([], True, Outcome.UNKNOWN),
        ([], False, Outcome.UNKNOWN),
        ([True], True, Outcome.VERIFIED),
        ([True], False, Outcome.UNKNOWN),
        ([False], True, Outcome.NEEDS_ATTENTION),
        ([True, True], True, Outcome.NEEDS_ATTENTION),
        ([True, False], True, Outcome.NEEDS_ATTENTION),
        ([False, False], False, Outcome.NEEDS_ATTENTION),
    ],
)
def test_search_absence_and_duplicates_never_mean_safe_retry(matches, complete, outcome):
    assert reconciliation(matches, complete=complete) == outcome
