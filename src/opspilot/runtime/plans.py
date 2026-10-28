"""F11 local immutable plans. Every node re-reads the fenced per-intent ledger."""

import re
from typing import Any
from uuid import UUID, uuid5

from langgraph.types import interrupt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.agent.evidence import canonical_proposal
from opspilot.config import Settings
from opspilot.contracts.actions import CommentProposal
from opspilot.contracts.plans import DeferredComment, MixedPlan, PlanItem
from opspilot.db.models_plans import PlanSlot, RunPlan
from opspilot.db.models_workflow import Action, Approval
from opspilot.runtime.actions import Conflict, prepare
from opspilot.runtime.fencing import current_engine
from opspilot.security.revisions import canonical_hash
from opspilot.tenancy.context import require_tenant
from opspilot.tenancy.session import TenantSession

VERSION = "full-graph-v2"
TERMINAL = {
    "verified",
    "rejected",
    "skipped_dependency",
    "unknown",
    "mismatch",
    "failed",
    "cancelled",
}


def wants_mixed(request: str) -> bool:
    return bool(re.search(r"\bnotify\b|\binbox\b|\bcomment\b|уведом|комментар", request, re.I))


def engine() -> AsyncEngine:
    value = current_engine()
    if value is None:
        raise Conflict("Fenced plan execution required")
    return value


async def canonical_plan(state: Any) -> MixedPlan | None:
    if not wants_mixed(state["request"]):
        return None
    ticket = canonical_proposal(state)
    actions = [PlanItem(key="ticket", tool="create_ticket", arguments=ticket)]
    if re.search(r"\bnotify\b|\binbox\b|уведом", state["request"], re.I):
        async with TenantSession(engine()) as session, session.begin():
            candidates = await session.scalars(
                text(
                    "SELECT user_id FROM identity.tenant_memberships "
                    "WHERE tenant_id=identity.current_tenant() "
                    "AND role='approver' ORDER BY user_id LIMIT 10"
                )
            )
            recipient = None
            for user in candidates:
                if await session.scalar(
                    text("SELECT identity.lock_role(:u,:t,'approver')"),
                    {"u": user, "t": require_tenant()},
                ):
                    recipient = user
                    break
        if recipient is None:
            raise Conflict("No enabled configured internal approver recipient")
        from opspilot.contracts.actions import NotificationProposal

        actions.append(
            PlanItem(
                key="inbox",
                tool="notify_manager",
                arguments=NotificationProposal(
                    customer_id=ticket.customer_id,
                    recipient_id=recipient,
                    body=(ticket.title + "\n" + ticket.description)[:6000],
                    evidence_ids=ticket.evidence_ids,
                ),
            )
        )
    if re.search(r"\bcomment\b|комментар", state["request"], re.I):
        actions.append(
            PlanItem(
                key="comment",
                tool="add_ticket_comment",
                depends_on=["ticket"],
                arguments=DeferredComment(
                    ticket_from="ticket",
                    customer_id=ticket.customer_id,
                    body=ticket.description,
                    evidence_ids=ticket.evidence_ids,
                ),
            )
        )
    return MixedPlan(actions=actions)


async def load(session: TenantSession, run: UUID) -> tuple[RunPlan | None, list[PlanSlot]]:
    plan = await session.scalar(select(RunPlan).where(RunPlan.run_id == run))
    if plan is None:
        return None, []
    if canonical_hash(plan.document) != plan.document_hash:
        raise Conflict("Corrupt plan digest")
    MixedPlan.model_validate(plan.document)
    slots = list(
        await session.scalars(
            select(PlanSlot).where(PlanSlot.plan_id == plan.id).order_by(PlanSlot.ordinal).limit(4)
        )
    )
    if not 1 <= len(slots) <= 3:
        raise Conflict("Corrupt bounded plan slots")
    return plan, slots


def binding(plan: RunPlan, slot: PlanSlot) -> dict[str, Any]:
    return {
        "plan_id": str(plan.id),
        "slot_id": str(slot.id),
        "hash": plan.document_hash,
        "wave": slot.wave,
        "dependencies": slot.dependencies,
        "intent": slot.key,
    }


async def materialize(
    session: TenantSession, plan: RunPlan, slot: PlanSlot, settings: Settings, slots: list[PlanSlot]
) -> None:
    if slot.action_id is not None:
        return
    args = dict(slot.template)
    if "ticket_from" in args:
        source = next(s for s in slots if s.key == args.pop("ticket_from"))
        action = await session.get(Action, source.action_id)
        if source.status != "verified" or action is None or not action.execution_result:
            return
        args["ticket_id"] = action.execution_result["ticket_id"]
        args = CommentProposal.model_validate(args).model_dump(mode="json")
    action = await prepare(
        session,
        slot.run_id,
        args,
        settings,
        tool=slot.tool,
        intent_id=slot.id,
        plan_binding=binding(plan, slot),
    )
    slot.action_id = action.id
    await session.flush()


async def prepare_plan(
    session: TenantSession, run: UUID, proposal: MixedPlan, settings: Settings
) -> RunPlan:
    await session.execute(text("SELECT workflow.check_fence(:r)"), {"r": run})
    doc = proposal.model_dump(mode="json")
    digest = canonical_hash(doc)
    previous = await session.scalar(select(RunPlan).where(RunPlan.run_id == run))
    if previous:
        if previous.document_hash != digest or previous.document != doc:
            raise Conflict("A business plan cannot replace completed or pending intents")
        return previous
    plan = RunPlan(id=uuid5(run, "local-plan-v1"), run_id=run, document=doc, document_hash=digest)
    session.add(plan)
    await session.flush()
    slots = []
    for ordinal, (item, wave) in enumerate(proposal.ordered()):
        slot = PlanSlot(
            id=uuid5(plan.id, item.key),
            run_id=run,
            plan_id=plan.id,
            key=item.key,
            ordinal=ordinal,
            wave=wave,
            tool=item.tool,
            template=item.arguments.model_dump(mode="json"),
            dependencies=item.depends_on,
            status="prepared",
        )
        session.add(slot)
        slots.append(slot)
    await session.flush()
    for slot in slots:
        if slot.wave == 1:
            await materialize(session, plan, slot, settings, slots)
    return plan


async def pending_wave(session: TenantSession, run: UUID) -> tuple[int, list[Action], bool]:
    plan, slots = await load(session, run)
    if plan is None:
        return 0, [], False
    remaining = [s for s in slots if s.status == "prepared"]
    if not remaining:
        return 0, [], False
    wave = min(s.wave for s in remaining)
    actions = []
    pending = False
    for slot in remaining:
        if slot.wave != wave or slot.action_id is None:
            continue
        action = await session.get(Action, slot.action_id)
        approval = await session.scalar(
            select(Approval).where(Approval.action_id == slot.action_id)
        )
        if action is None or approval is None:
            raise Conflict("Missing bound action")
        actions.append(action)
        pending = pending or approval.decision == "pending"
    return wave, actions, pending


async def prepare_node(state: Any, runtime: Any) -> None:
    async with TenantSession(engine()) as session, session.begin():
        plan = await prepare_plan(
            session,
            UUID(state["run_id"]),
            MixedPlan.model_validate(state["proposed_plan"]),
            runtime.settings,
        )
        state["plan_id"] = str(plan.id)
        state["outcome"] = None


async def wait_node(state: Any, runtime: Any) -> None:
    ref = interrupt(
        {
            "plan_id": state["plan_id"],
            "wave": state["plan_wave"],
            "action_ids": state["plan_waiting"],
        }
    )
    if not isinstance(ref, dict) or set(ref) != {"action_id"}:
        raise Conflict("Invalid plan resume reference")
    async with TenantSession(engine()) as session:
        plan, slots = await load(session, UUID(state["run_id"]))
        if plan is None or str(plan.id) != state["plan_id"]:
            raise Conflict("Plan binding mismatch")
        wave, actions, pending = await pending_wave(session, UUID(state["run_id"]))
        if (
            pending
            or ref["action_id"] not in {str(a.id) for a in actions}
            or wave != state["plan_wave"]
        ):
            raise Conflict("Incomplete or cross-wave resume")
    state["plan_waiting"] = []
    state["outcome"] = None


async def reserve_verification(action: UUID) -> None:
    from opspilot.agent.budgets import BudgetExceeded

    async with TenantSession(engine()) as session, session.begin():
        changed = await session.execute(
            text("""UPDATE workflow.plan_slots SET verify_attempts=verify_attempts+1
          WHERE tenant_id=identity.current_tenant() AND action_id=:a
          AND status='prepared' AND verify_attempts<3 RETURNING id"""),
            {"a": action},
        )
        if changed.first() is None:
            raise BudgetExceeded("Per-action verification reserve exhausted")


async def after_verified(slot: UUID) -> None:
    """Private fault-injection seam; no user/config hook or external side effect."""


async def step_node(state: Any, runtime: Any) -> None:
    from opspilot.agent.nodes.execute import execute
    from opspilot.agent.nodes.verify import verify

    run = UUID(state["run_id"])
    state["plan_waiting"] = []
    state["outcome"] = None
    selected = None
    async with TenantSession(engine()) as session, session.begin():
        await session.execute(text("SELECT workflow.check_fence(:r)"), {"r": run})
        plan, slots = await load(session, run)
        if plan is None or str(plan.id) != state["plan_id"]:
            raise Conflict("Plan binding mismatch")
        # Rejections and failed prerequisites are monotone; never touch a completed effect.
        for slot in slots:
            if slot.status != "prepared":
                continue
            if slot.action_id:
                approval = await session.scalar(
                    select(Approval).where(Approval.action_id == slot.action_id)
                )
                if approval and approval.decision in {
                    "rejected",
                    "expired",
                    "revoked",
                    "superseded",
                }:
                    slot.status = "rejected"
            deps = [s for s in slots if s.key in slot.dependencies]
            if any(d.status in TERMINAL - {"verified"} for d in deps):
                slot.status = "skipped_dependency"
                if slot.action_id:
                    action = await session.get(Action, slot.action_id)
                    if action and action.execution_status == "not_started":
                        action.execution_status = "skipped_dependency"
        await session.flush()
        remaining = [s for s in slots if s.status == "prepared"]
        if not remaining:
            state["plan_done"] = True
            return
        wave = min(s.wave for s in remaining)
        state["plan_wave"] = wave
        for slot in remaining:
            if slot.wave == wave:
                await materialize(session, plan, slot, runtime.settings, slots)
        _, actions, pending = await pending_wave(session, run)
        if pending:
            state["plan_waiting"] = [str(a.id) for a in actions]
            return
        selected = next(
            (
                s
                for s in remaining
                if s.wave == wave
                and s.action_id
                and all(d.status == "verified" for d in slots if d.key in s.dependencies)
            ),
            None,
        )
        if selected is None:
            raise Conflict("No executable bounded DAG action")
        action = await session.get(Action, selected.action_id)
        assert action is not None
        if action.execution_status in {"unknown", "failed", "skipped_dependency"}:
            selected.status = "unknown" if action.execution_status == "unknown" else "failed"
            return
        await session.execute(text("SELECT workflow.check_plan_action(:a)"), {"a": action.id})
        action_id = action.id
        slot_id = selected.id
    state["action_id"] = str(action_id)
    state["execution_result"] = None
    state["verification_result"] = None
    await execute(state, runtime)
    if state.get("execution_result"):
        runtime.plan_verification_action = action_id
        try:
            await verify(state, runtime)
        finally:
            runtime.plan_verification_action = None
    verification = state.get("verification_result") or {"status": "not_started"}
    status = (
        "verified"
        if verification["status"] == "verified"
        else "mismatch"
        if verification["status"] == "mismatch"
        else "unknown"
        if state.get("execution_result") or state.get("outcome") == "unknown_outcome"
        else "failed"
    )
    async with TenantSession(engine()) as session, session.begin():
        slot = await session.get(PlanSlot, slot_id)
        assert slot is not None
        if slot.status == "prepared":
            slot.status = status
            slot.verification = verification
    await after_verified(slot_id)
    state["outcome"] = None


async def report_node(state: Any, runtime: Any) -> None:
    async with TenantSession(engine()) as session:
        _, slots = await load(session, UUID(state["run_id"]))
        effects = []
        for slot in slots:
            action = await session.get(Action, slot.action_id) if slot.action_id else None
            approval = (
                await session.scalar(select(Approval).where(Approval.action_id == slot.action_id))
                if slot.action_id
                else None
            )
            effects.append(
                {
                    "action_id": str(slot.action_id) if slot.action_id else None,
                    "key": slot.key,
                    "tool_name": slot.tool,
                    "status": slot.status,
                    "approval_status": approval.decision if approval else "not_ready",
                    "verification_status": slot.verification["status"],
                    "result": action.execution_result if action else None,
                    "wave": slot.wave,
                    "dependencies": slot.dependencies,
                }
            )
    statuses = [s.status for s in slots]
    outcome = (
        "actions_verified"
        if all(s == "verified" for s in statuses)
        else "actions_partially_verified"
        if "verified" in statuses
        else "unknown_outcome"
        if "unknown" in statuses
        else "rejected"
        if all(s in {"rejected", "skipped_dependency"} for s in statuses)
        else state.get("outcome") or "partial"
    )
    state["outcome"] = outcome
    state["final_report"] = {
        "summary": "Local plan outcomes are recorded per action.",
        "facts": state.get("facts", []),
        "hypotheses": state.get("hypotheses", []),
        "missing_checks": state.get("missing_checks", []),
        "action_summary": "; ".join(s.key + ": " + s.status for s in slots),
        "ticket_id": next(
            (
                e["result"].get("ticket_id")
                for e in effects
                if e["result"] and e["tool_name"] == "create_ticket"
            ),
            None,
        ),
        "verification_status": "verified" if outcome == "actions_verified" else "unknown",
        "remaining_problem": (
            "Internal persistence does not confirm external recovery or human reading."
        ),
        "outcome": outcome,
        "effects": effects,
    }
    state["budget"] = runtime.budget.snapshot()


async def projection(
    session: TenantSession, run: UUID
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    plan, slots = await load(session, run)
    if plan is None:
        return None, []
    wave, _, _ = await pending_wave(session, run)
    nodes = []
    actions = []
    for slot in slots:
        nodes.append(
            {
                "slot_id": str(slot.id),
                "key": slot.key,
                "tool_name": slot.tool,
                "status": slot.status,
                "dependencies": slot.dependencies,
                "wave": slot.wave,
                "action_id": str(slot.action_id) if slot.action_id else None,
            }
        )
        if not slot.action_id:
            continue
        a = await session.get(Action, slot.action_id)
        p = await session.scalar(select(Approval).where(Approval.action_id == slot.action_id))
        assert a is not None and p is not None
        actions.append(
            {
                "action_id": str(a.id),
                "revision_id": str(a.id),
                "logical_action_id": str(a.logical_action_id),
                "tool_name": a.tool_name,
                "arguments": a.arguments,
                "arguments_hash": a.arguments_hash,
                "revision_hash": a.revision_hash,
                "expected_version": p.version,
                "expires_at": p.expires_at.isoformat(),
                "approval_status": p.decision,
                "execution_status": a.execution_status,
                "result": a.execution_result,
                "verification": slot.verification,
                "wave": slot.wave,
                "key": slot.key,
                "plan_status": slot.status,
            }
        )
    return {
        "plan_id": str(plan.id),
        "version": 1,
        "hash": plan.document_hash,
        "wave": wave,
        "verification_reads": sum(s.verify_attempts for s in slots),
        "nodes": nodes,
    }, actions


async def recover_plan(service: Any, run: Any, saved: Any, values: dict[str, Any]) -> bool:
    from sqlalchemy import update

    from opspilot.agent.service import project
    from opspilot.db.models_workflow import AgentRun

    async with TenantSession(service.engine) as session:
        plan, slots = await load(session, run.id)
        if plan is None:
            return False
        if run.workflow_version != VERSION or values.get("workflow_version") != VERSION:
            raise ValueError("Plan workflow binding")
        if values.get("plan_id") is None:
            if set(saved.next) != {"prepare_approval"}:
                raise ValueError("Unbound persisted plan")
        elif values["plan_id"] != str(plan.id):
            raise ValueError("Foreign plan checkpoint")
        wave, actions, pending = await pending_wave(session, run.id)
        interrupted = any(task.interrupts for task in saved.tasks)
    if interrupted:
        if not actions or values.get("plan_wave") != wave:
            raise ValueError("Approval wave checkpoint binding")
        if not pending:
            await service.resume(run.id, actions[-1].id)
            return True
        public = project({**values, "__interrupt__": True})
        status = "waiting_for_approval"
    elif saved.next:
        await service.resume(run.id, UUID(int=0), continuation=True)
        return True
    elif values.get("final_report"):
        public = project(values)
        status = public["status"]
    else:
        raise ValueError("Unsupported plan checkpoint")
    for key in ("trace_context", "continuation_context"):
        public[key] = run.public_snapshot.get(key)
    async with service.engine.begin() as conn:
        await conn.execute(
            update(AgentRun)
            .where(AgentRun.id == run.id)
            .values(
                status=status,
                public_snapshot=public,
                outcome=values.get("outcome"),
                usage=values["budget"],
            )
        )
    return True
