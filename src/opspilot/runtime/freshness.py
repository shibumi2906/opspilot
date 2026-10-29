"""One run-wide replan, immutable replacement and persisted per-action read allowance."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from opspilot.config import Settings
from opspilot.db.models_workflow import Action, AgentRun, Approval, LogicalAction
from opspilot.runtime.actions import Conflict, new_revision
from opspilot.runtime.fencing import current_engine
from opspilot.security.freshness import PreconditionsChanged, check
from opspilot.tenancy.session import TenantSession


async def replace(
    session: TenantSession, old: Action, arguments: dict[str, Any], settings: Settings
) -> Action:
    # Match checkpoint/local-effect order: lease row before run/intent rows.
    await session.execute(text("SELECT workflow.check_fence(:r)"), {"r": old.run_id})
    logical = await session.scalar(
        select(LogicalAction).where(LogicalAction.id == old.logical_action_id).with_for_update()
    )
    run = await session.scalar(select(AgentRun).where(AgentRun.id == old.run_id).with_for_update())
    assert logical is not None and run is not None
    if (
        old.execution_status != "not_started"
        or old.superseded_at
        or run.cancellation
        or logical.current_revision_id != old.id
    ):
        raise Conflict("Cannot replan a completed/uncertain/superseded intent")
    if old.plan_binding and await session.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM workflow.plan_slots WHERE "
            "tenant_id=identity.current_tenant() AND run_id=:r AND wave>1)"
        ),
        {"r": old.run_id},
    ):
        raise Conflict("Replan would exceed two approval waves")
    changed = await session.execute(
        text(
            "UPDATE workflow.agent_runs SET replan_count=replan_count+1 WHERE id=:r "
            "AND tenant_id=identity.current_tenant() AND replan_count<1 RETURNING id"
        ),
        {"r": old.run_id},
    )
    if changed.first() is None:
        raise Conflict("Run replan limit reached")
    approval = await session.scalar(
        select(Approval).where(Approval.action_id == old.id).with_for_update()
    )
    assert approval is not None
    if approval.decision not in {"pending", "approved"}:
        raise Conflict("Approval is terminal")
    approval.decision = "superseded"
    old.superseded_at = await session.scalar(select(func.clock_timestamp()))
    await session.execute(
        text(
            "UPDATE workflow.execution_grants SET revoked_at=clock_timestamp() "
            "WHERE tenant_id=identity.current_tenant() AND revision_id=:a AND revoked_at IS NULL"
        ),
        {"a": old.id},
    )
    logical.version += 1
    logical.current_revision_id = uuid4()
    await session.flush()
    new = await new_revision(session, logical, arguments, settings, old.tool_name, old.plan_binding)
    if old.plan_binding:
        from opspilot.db.models_plans import PlanSlot

        slot = await session.get(PlanSlot, old.logical_action_id)
        if slot is None or slot.status != "prepared" or slot.action_id != old.id:
            raise Conflict("Replan slot mismatch")
        slot.action_id = new.id
    await session.flush()
    return new


async def after_replanned(action: UUID) -> None:
    """Private process fault-injection seam after transaction commit, before checkpoint."""


async def before_dispatch(state: Any, runtime: Any) -> bool:
    engine = current_engine()
    assert engine is not None
    try:
        async with TenantSession(engine) as session, session.begin():
            action = await session.get(Action, UUID(state["action_id"]))
            assert action is not None
            logical = await session.get(LogicalAction, action.logical_action_id)
            if logical and logical.current_revision_id != action.id:
                action = await session.get(Action, logical.current_revision_id)
                assert action is not None
                state["action_id"] = str(action.id)
            approval = await session.scalar(select(Approval).where(Approval.action_id == action.id))
            if approval and approval.decision == "pending":
                state["freshness_reapproval"] = True
                state["outcome"] = None
                return False
            try:
                await check(session, action, runtime.settings)
                return True
            except PreconditionsChanged as exc:
                if exc.code != "PRECONDITIONS_CHANGED":
                    state["missing_checks"] = sorted(
                        set(state.get("missing_checks", [])) | {exc.code}
                    )
                    state["outcome"] = "partial"
                    state.setdefault("errors", {})["freshness"] = {
                        "code": exc.code,
                        "node": "execute",
                    }
                    return False
            new = await replace(session, action, action.arguments, runtime.settings)
            state["action_id"] = str(new.id)
            state["freshness_reapproval"] = True
            state["outcome"] = None
        await after_replanned(UUID(state["action_id"]))
        return False
    except Conflict as exc:
        state["outcome"] = "partial"
        state.setdefault("errors", {})["freshness"] = {
            "code": "REPLAN_WAVE_LIMIT" if "waves" in str(exc) else "REPLAN_LIMIT",
            "node": "execute",
        }
        return False


async def reserve_verification(action: UUID) -> None:
    from opspilot.agent.budgets import BudgetExceeded

    engine = current_engine()
    assert engine is not None
    async with TenantSession(engine) as session, session.begin():
        row = await session.get(Action, action)
        if row is None:
            raise BudgetExceeded("Missing verification action")
        await session.execute(
            text(
                "INSERT INTO workflow.action_read_budgets(action_id,run_id) VALUES(:a,:r) "
                "ON CONFLICT(action_id) DO NOTHING"
            ),
            {"a": action, "r": row.run_id},
        )
        changed = await session.execute(
            text(
                "UPDATE workflow.action_read_budgets SET attempts=attempts+1 "
                "WHERE tenant_id=identity.current_tenant() AND action_id=:a "
                "AND attempts<3 RETURNING action_id"
            ),
            {"a": action},
        )
        if changed.first() is None:
            raise BudgetExceeded("Per-action verification reserve exhausted")
