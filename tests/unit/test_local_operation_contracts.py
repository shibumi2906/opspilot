from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot.contracts.actions import CommentProposal, NotificationProposal
from opspilot.security.revisions import canonical_hash, document


@pytest.mark.parametrize(
    "kind,model,key",
    [
        ("add_ticket_comment", CommentProposal, "ticket_id"),
        ("notify_manager", NotificationProposal, "recipient_id"),
    ],
)
def test_exact_bounded_plain_text_contract(kind, model, key):
    payload = {
        "customer_id": str(uuid4()),
        key: str(uuid4()),
        "body": "<script>alert(1)</script>",
        "evidence_ids": ["e2", "e1", "e1"],
    }
    validated = model.model_validate(payload).model_dump(mode="json")
    assert validated["body"] == payload["body"]
    assert validated["evidence_ids"] == ["e1", "e2"]
    args = dict(
        tenant=str(uuid4()),
        run=str(uuid4()),
        logical=str(uuid4()),
        revision=str(uuid4()),
        version=1,
        arguments=validated,
        expires=datetime.now(UTC),
        tool=kind,
    )
    base = canonical_hash(document(**args))
    for field in (key, "customer_id", "body", "evidence_ids"):
        changed = {**validated, field: ["other"] if field == "evidence_ids" else str(uuid4())}
        assert canonical_hash(document(**{**args, "arguments": changed})) != base
    for change in (
        {"body": ""},
        {"body": "x" * 6001},
        {"url": "https://example.invalid"},
        {"evidence_ids": []},
    ):
        with pytest.raises(ValidationError):
            model.model_validate({**payload, **change})


@pytest.mark.parametrize(
    "kind,allowed,hidden",
    [
        ("add_ticket_comment", "ticket_id", "recipient_id"),
        ("notify_manager", "recipient_id", "ticket_id"),
    ],
)
def test_public_export_is_operation_specific(kind, allowed, hidden):
    from opspilot.contracts.public import public_snapshot

    payload = {
        "customer_id": "customer",
        allowed: "target",
        hidden: "private-target",
        "body": "<script>text</script>",
        "evidence_ids": ["e1"],
        "secret": "private",
    }
    exported = public_snapshot(
        {
            "action": {
                "tool_name": kind,
                "arguments": payload,
                "result": {"comment_id": "id", "grant": "private"},
            }
        }
    )["action"]
    assert exported["arguments"] == {
        k: payload[k] for k in ("customer_id", allowed, "body", "evidence_ids")
    }
    assert "private" not in str(exported)
