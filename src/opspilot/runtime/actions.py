"""Immutable workflow actions; no domain access."""

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.db.models_workflow import Action, Approval


class Conflict(Exception):
    pass


def payload_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


async def prepare(session: AsyncSession, run_id: UUID, arguments: dict[str, Any]) -> Action:
    action = await session.scalar(select(Action).where(Action.run_id == run_id))
    digest = payload_hash(arguments)
    if action:
        if action.arguments_hash != digest or action.arguments != arguments:
            raise Conflict("Immutable action differs from replay")
        return action
    action = Action(
        id=uuid4(),
        run_id=run_id,
        tool_name="create_ticket",
        arguments=arguments,
        arguments_hash=digest,
    )
    session.add(action)
    await session.flush()
    session.add(Approval(id=uuid4(), action_id=action.id, decision="pending"))
    return action
