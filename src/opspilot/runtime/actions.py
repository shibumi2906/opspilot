"""Immutable revision preparation; active pointer selects the revision under review."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from opspilot.config import Settings
from opspilot.db.models_workflow import Action, Approval, LogicalAction
from opspilot.security.revisions import canonical_hash, document
from opspilot.tenancy.context import require_tenant
from opspilot.tenancy.session import TenantSession as AsyncSession


class Conflict(Exception):
    pass


def payload_hash(arguments: dict[str, Any]) -> str:
    return canonical_hash(arguments)


async def new_revision(
    session: AsyncSession,
    logical: LogicalAction,
    arguments: dict[str, Any],
    settings: Settings,
    tool: str = "create_ticket",
) -> Action:
    now = await session.scalar(select(func.clock_timestamp()))
    assert now is not None
    expires = now + timedelta(seconds=settings.approval_ttl_seconds)
    revision = logical.current_revision_id
    doc = document(
        tenant=str(require_tenant()),
        run=str(logical.run_id),
        logical=str(logical.id),
        revision=str(revision),
        version=logical.version,
        plan_version=logical.version,
        arguments=arguments,
        expires=expires,
        tool=tool,
    )
    action = Action(
        id=revision,
        run_id=logical.run_id,
        logical_action_id=logical.id,
        revision_number=logical.version,
        plan_version=logical.version,
        revision_document=doc,
        revision_hash=canonical_hash(doc),
        expires_at=expires,
        tool_name=tool,
        arguments=arguments,
        arguments_hash=payload_hash(arguments),
    )
    session.add(action)
    await session.flush()
    session.add(
        Approval(
            id=uuid4(),
            action_id=action.id,
            decision="pending",
            version=logical.version,
            expires_at=expires,
        )
    )
    await session.flush()
    return action


async def prepare(
    session: AsyncSession,
    run_id: UUID,
    arguments: dict[str, Any],
    settings: Settings | None = None,
    *,
    tool: str = "create_ticket",
) -> Action:
    from opspilot.mcp_client.registry import WRITE_TOOLS

    arguments = (
        WRITE_TOOLS[tool]
        .arguments.model_validate({"run_id": run_id, "action_id": run_id, "arguments": arguments})
        .model_dump(mode="json")["arguments"]
    )
    action = await session.scalar(
        select(Action)
        .where(Action.run_id == run_id, Action.superseded_at.is_(None))
        .order_by(Action.created_at.desc())
        .limit(1)
    )
    if action:
        if (
            action.tool_name != tool
            or action.arguments_hash != payload_hash(arguments)
            or action.arguments != arguments
        ):
            raise Conflict("Immutable action differs from replay")
        return action
    logical = LogicalAction(id=uuid4(), run_id=run_id, current_revision_id=uuid4(), version=1)
    session.add(logical)
    await session.flush()
    return await new_revision(session, logical, arguments, settings or Settings(), tool)


async def expire_approvals(service: Any) -> None:
    """Bounded worker sweep, same approval row lock as decisions; DB time is authoritative."""
    from opspilot.runtime.fencing import execution_lease
    from opspilot.runtime.jobs import enqueue

    async with service.engine.connect() as conn:
        ids = list(
            await conn.scalars(
                text("""SELECT DISTINCT a.run_id FROM workflow.approvals p
          JOIN workflow.actions a ON a.id=p.action_id AND a.tenant_id=p.tenant_id
          WHERE p.tenant_id=identity.current_tenant() AND p.decision IN ('pending','approved')
          AND p.expires_at<=clock_timestamp() AND a.execution_status='not_started'
          AND a.superseded_at IS NULL LIMIT 100""")
            )
        )
    for run in ids:
        async with execution_lease(service.engine, run, service.settings):
            async with AsyncSession(service.engine) as conn, conn.begin():
                rows = list(
                    await conn.scalars(
                        text("""UPDATE workflow.approvals p SET decision='expired'
                 FROM workflow.actions a WHERE a.id=p.action_id AND
a.tenant_id=p.tenant_id
                 AND a.run_id=:r AND a.tenant_id=identity.current_tenant()
                 AND p.decision IN ('pending','approved') AND
p.expires_at<=clock_timestamp()
                 AND a.execution_status='not_started' AND a.superseded_at IS NULL
RETURNING p.action_id"""),
                        {"r": run},
                    )
                )
                if rows:
                    await conn.execute(
                        text(
                            "UPDATE workflow.agent_runs SET status='running' WHERE id=:r "
                            "AND status='waiting_for_approval'"
                        ),
                        {"r": run},
                    )
                    # Re-arm a completed resume for a newer expired revision as well.
                    await enqueue(conn, run, "resume", rows[0])
