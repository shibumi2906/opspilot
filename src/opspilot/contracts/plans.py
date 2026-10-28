"""Bounded local DAG. The model proposes data, never capabilities or future object IDs."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from opspilot.contracts.actions import CommentProposal, NotificationProposal, TicketProposal
from opspilot.contracts.common import StrictModel

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class DeferredComment(StrictModel):
    ticket_from: Key
    body: Annotated[str, StringConstraints(min_length=1, max_length=6000)]
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=30)]
    customer_id: UUID


class PlanItem(StrictModel):
    key: Key
    tool: Literal["create_ticket", "add_ticket_comment", "notify_manager"]
    arguments: TicketProposal | CommentProposal | NotificationProposal | DeferredComment
    depends_on: Annotated[list[Key], Field(max_length=2)] = []

    @model_validator(mode="after")
    def exact_type(self) -> "PlanItem":
        expected = {
            "create_ticket": (TicketProposal,),
            "add_ticket_comment": (CommentProposal, DeferredComment),
            "notify_manager": (NotificationProposal,),
        }
        if not isinstance(self.arguments, expected[self.tool]):
            raise ValueError("Tool argument schema mismatch")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("Duplicate dependency")
        if (
            isinstance(self.arguments, DeferredComment)
            and self.arguments.ticket_from not in self.depends_on
        ):
            raise ValueError("Deferred ticket must be an explicit dependency")
        return self


class MixedPlan(StrictModel):
    schema_version: Literal[1] = 1
    actions: Annotated[list[PlanItem], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def dag(self) -> "MixedPlan":
        by_key = {a.key: a for a in self.actions}
        if len(by_key) != len(self.actions):
            raise ValueError("Duplicate action key")
        intents = set()
        customer = None
        for a in self.actions:
            if any(d not in by_key or d == a.key for d in a.depends_on):
                raise ValueError("Unknown/self dependency")
            if (
                isinstance(a.arguments, DeferredComment)
                and by_key[a.arguments.ticket_from].tool != "create_ticket"
            ):
                raise ValueError("Deferred target must be a ticket action")
            doc = a.arguments.model_dump_json()
            intent = (a.tool, doc)
            if intent in intents:
                raise ValueError("Duplicate business intent")
            intents.add(intent)
            if customer is None:
                customer = a.arguments.customer_id
            if customer != a.arguments.customer_id:
                raise ValueError("Plan crosses customer scope")
        self.ordered()  # validates cycles and wave bound
        return self

    def ordered(self) -> list[tuple[PlanItem, int]]:
        waiting = {a.key: a for a in self.actions}
        waves: dict[str, int] = {}
        result = []
        while waiting:
            ready = next((a for a in waiting.values() if set(a.depends_on) <= waves.keys()), None)
            if ready is None:
                raise ValueError("Cyclic plan")
            wave = max([waves[d] for d in ready.depends_on] + [1])
            if isinstance(ready.arguments, DeferredComment):
                wave = max(wave, waves[ready.arguments.ticket_from] + 1)
            if wave > 2:
                raise ValueError("Approval wave limit")
            result.append((ready, wave))
            waves[ready.key] = wave
            del waiting[ready.key]
        return result
