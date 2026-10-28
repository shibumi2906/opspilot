from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot.contracts.plans import MixedPlan
from opspilot.security.revisions import canonical_hash, document


def ticket(key="ticket", deps=None):
    return {
        "key": key,
        "tool": "create_ticket",
        "depends_on": deps or [],
        "arguments": {
            "customer_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "title": "Approved title",
            "description": "Synthetic body",
            "priority": "medium",
            "evidence_ids": ["e1"],
        },
    }


def comment(key="comment", source="ticket"):
    return {
        "key": key,
        "tool": "add_ticket_comment",
        "depends_on": [source],
        "arguments": {
            "customer_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "ticket_from": source,
            "body": "Approved comment",
            "evidence_ids": ["e1"],
        },
    }


@pytest.mark.parametrize(
    "actions",
    [
        [ticket(), comment()],
        [comment(), ticket()],
    ],
)
def test_known_order_and_separate_concrete_approval_wave(actions):
    ordered = MixedPlan.model_validate({"actions": actions}).ordered()
    assert [(item.key, wave) for item, wave in ordered] == [("ticket", 1), ("comment", 2)]


@pytest.mark.parametrize(
    "actions",
    [
        [ticket(deps=["missing"])],
        [ticket(deps=["ticket"])],
        [ticket(deps=["other"]), ticket("other", ["ticket"])],
        [ticket(), ticket()],
        [ticket(), ticket("copy")],
        [ticket(), comment(), comment("other_comment", "ticket")],
        [ticket("a"), ticket("b"), ticket("c"), ticket("d")],
        [
            ticket(),
            comment("c1"),
            {
                "key": "t2",
                "tool": "create_ticket",
                "depends_on": ["c1"],
                "arguments": {**ticket()["arguments"], "title": "Different"},
            },
            comment("c2", "t2"),
        ],
    ],
)
def test_invalid_unbounded_or_duplicate_intents_denied(actions):
    with pytest.raises(ValidationError):
        MixedPlan.model_validate({"actions": actions})


def test_tool_type_scope_and_capability_fields_denied():
    payload = ticket()
    payload["tool"] = "notify_manager"
    with pytest.raises(ValidationError):
        MixedPlan.model_validate({"actions": [payload]})
    payload = ticket()
    payload["arguments"]["grant"] = "forged"
    with pytest.raises(ValidationError):
        MixedPlan.model_validate({"actions": [payload]})
    payload = comment()
    payload["arguments"]["customer_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        MixedPlan.model_validate({"actions": [ticket(), payload]})


def test_each_plan_wave_dependency_intent_is_bound_into_approval_digest():
    args = ticket()["arguments"]
    binding = {
        "plan_id": str(uuid4()),
        "slot_id": str(uuid4()),
        "hash": "a" * 64,
        "wave": 1,
        "dependencies": [],
        "intent": "ticket",
    }
    values = dict(
        tenant=str(uuid4()),
        run=str(uuid4()),
        logical=str(uuid4()),
        revision=str(uuid4()),
        version=1,
        arguments=args,
        expires=datetime.now(UTC),
        plan_binding=binding,
    )
    original = canonical_hash(document(**values))
    for key, value in [
        ("wave", 2),
        ("dependencies", ["inbox"]),
        ("intent", "other"),
        ("slot_id", str(uuid4())),
        ("plan_id", str(uuid4())),
        ("hash", "b" * 64),
    ]:
        assert (
            canonical_hash(document(**{**values, "plan_binding": {**binding, key: value}}))
            != original
        )
