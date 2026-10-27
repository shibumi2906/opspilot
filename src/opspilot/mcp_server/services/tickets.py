"""The MCP-only atomic ticket write. Fault hooks are private test dependencies."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.auth.context import AuthError, actor_id
from opspilot.config import Settings
from opspilot.contracts.tools import CreateTicketArgs, CreateTicketData
from opspilot.db.models_domain import Ticket
from opspilot.db.models_workflow import Action, AgentRun, Approval, LogicalAction
from opspilot.runtime.actions import payload_hash
from opspilot.security.grants import consume
from opspilot.security.revisions import valid_revision
from opspilot.tenancy.session import TenantSession as AsyncSession


class WriteDenied(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


async def create_ticket(
    engine: AsyncEngine,
    args: CreateTicketArgs,
    *,
    settings: Settings | None = None,
    after_insert: Callable[[], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    settings = settings or Settings()
    arguments = args.arguments.model_dump(mode="json")
    async with AsyncSession(engine) as session, session.begin():
        action = await session.scalar(select(Action).where(Action.id == args.action_id))
        if action is None:
            raise WriteDenied("APPROVAL_REQUIRED")
        if action.run_id != args.run_id or action.tool_name != "create_ticket":
            raise WriteDenied("STATE_CONFLICT")
        if action.arguments != arguments or action.arguments_hash != payload_hash(arguments):
            raise WriteDenied("PAYLOAD_MISMATCH")
        await session.execute(text("SELECT workflow.check_fence(:r)"), {"r": args.run_id})
        action = await session.scalar(
            select(Action)
            .where(Action.id == args.action_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            action is None
            or action.run_id != args.run_id
            or action.arguments != arguments
            or action.arguments_hash != payload_hash(arguments)
        ):
            raise WriteDenied("PAYLOAD_MISMATCH")
        logical = await session.get(LogicalAction, action.logical_action_id)
        if (
            logical is None
            or logical.current_revision_id != action.id
            or action.superseded_at
            or not valid_revision(action)
        ):
            raise WriteDenied("STATE_CONFLICT")
        if not await session.scalar(text("SELECT workflow.lock_approval(:a)"), {"a": action.id}):
            raise WriteDenied("APPROVAL_REQUIRED")
        approval = await session.scalar(select(Approval).where(Approval.action_id == action.id))
        if approval is None or approval.decision != "approved":
            raise WriteDenied("APPROVAL_REQUIRED")
        run = await session.get(AgentRun, action.run_id)
        if (
            run is None
            or run.actor_id != actor_id()
            or approval.decided_by is None
            or approval.decided_at is None
        ):
            raise WriteDenied("APPROVAL_REQUIRED")
        for user, role in [(run.actor_id, "operator"), (approval.decided_by, "approver")]:
            allowed = await session.scalar(
                text("SELECT identity.lock_role(:u,:t,:r)"),
                {"t": run.tenant_id, "u": user, "r": role},
            )
            if not allowed:
                raise WriteDenied("APPROVAL_REQUIRED")
        same = run.actor_id == approval.decided_by
        if same and (not settings.allow_demo_self_approval or not approval.self_approval_exception):
            raise WriteDenied("APPROVAL_REQUIRED")
        now = await session.scalar(select(func.clock_timestamp()))
        assert now is not None
        if now >= approval.expires_at or now >= action.expires_at:
            raise WriteDenied("APPROVAL_EXPIRED")
        try:
            await consume(session, action, approval, run, settings)
        except AuthError as exc:
            raise WriteDenied(exc.code) from None
        if action.execution_result is not None:
            if action.execution_status != "succeeded":
                raise WriteDenied("STATE_CONFLICT")
            return (
                CreateTicketData.model_validate(action.execution_result)
                .model_copy(update={"replayed": True})
                .model_dump(mode="json")
            )
        if run.cancellation:
            raise WriteDenied("STATE_CONFLICT")
        await session.execute(text("SELECT workflow.check_not_cancelled(:r)"), {"r": args.run_id})
        ticket = Ticket(
            id=uuid4(),
            originating_action_id=action.id,
            customer_id=args.arguments.customer_id,
            title=args.arguments.title,
            description=args.arguments.description,
            priority=args.arguments.priority,
            evidence_ids=args.arguments.evidence_ids,
        )
        session.add(ticket)
        await session.flush()
        if after_insert is not None:
            await after_insert()
        result = CreateTicketData(
            ticket_id=ticket.id, created_at=ticket.created_at, replayed=False
        ).model_dump(mode="json")
        action.execution_status = "succeeded"
        action.execution_result = result
        action.executed_at = datetime.now(UTC)
        return result
