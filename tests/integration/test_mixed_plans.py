"""F11 real LangGraph/PostgreSQL/MCP plans, partial decisions and separate waves."""

import asyncio
import sys
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from opspilot.agent.service import run_investigation
from opspilot.contracts.api import Decision
from opspilot.contracts.plans import MixedPlan
from opspilot.db.models_plans import PlanSlot, RunPlan
from opspilot.runtime.actions import Conflict, payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.plans import prepare_plan, reserve_verification
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.security.grants import issue
from opspilot.tenancy.session import TenantSession

REQUEST = "Investigate GreenShop and notify manager and add a ticket comment"


async def pending(settings, request=REQUEST):
    value = await run_investigation(settings, request, mode="scripted")
    service = RunService(settings)
    run = UUID(value["run_id"])
    return service, run, await service.snapshot(run)


async def choose(service, run, action, choice):
    return await service.decide(
        run,
        Decision(
            action_id=action["action_id"],
            decision=choice,
            expected_version=action["expected_version"],
        ),
    )


async def counts(admin, run):
    async with admin.connect() as conn:
        result = {}
        for table in ["tickets", "ticket_comments", "notifications"]:
            result[table] = await conn.scalar(
                text(
                    f"SELECT count(*) FROM domain.{table} d JOIN workflow.actions a "
                    "ON a.tenant_id=d.tenant_id AND a.id=d.originating_action_id "
                    "WHERE a.run_id=:r"
                ),
                {"r": run},
            )
        return result


@pytest.mark.parametrize(
    "ticket_choice,inbox_choice,expected",
    [
        ("approve", "reject", {"ticket": "verified", "inbox": "rejected", "comment": "verified"}),
        (
            "reject",
            "approve",
            {"ticket": "rejected", "inbox": "verified", "comment": "skipped_dependency"},
        ),
        (
            "reject",
            "reject",
            {"ticket": "rejected", "inbox": "rejected", "comment": "skipped_dependency"},
        ),
    ],
)
async def test_mixed_subset_dependencies_and_concrete_second_wave(
    integration_settings, admin_engine, ticket_choice, inbox_choice, expected
):
    service, run, value = await pending(integration_settings)
    try:
        assert value["status"] == "waiting_for_approval", value
        assert value["plan"]["wave"] == 1 and len(value["plan"]["nodes"]) == 3
        assert len(value["actions"]) == 2 and all(
            a["tool_name"] != "add_ticket_comment" for a in value["actions"]
        )
        actions = {a["key"]: a for a in value["actions"]}
        first = await choose(service, run, actions["ticket"], ticket_choice)
        assert first["status"] == "waiting_for_approval"
        assert not await process_one(service, run)
        assert await counts(admin_engine, run) == {
            "tickets": 0,
            "ticket_comments": 0,
            "notifications": 0,
        }
        # A single sibling approval cannot issue any capability before its wave is decided.
        if ticket_choice == "approve":
            a = actions["ticket"]
            async with execution_lease(service.engine, run, integration_settings):
                with pytest.raises(DBAPIError):
                    await issue(
                        integration_settings,
                        {
                            "run": str(run),
                            "action": a["action_id"],
                            "hash": payload_hash(a["arguments"]),
                            "tool": "create_ticket",
                        },
                    )
        await choose(service, run, actions["inbox"], inbox_choice)
        await process_one(service, run)
        value = await service.snapshot(run)
        if ticket_choice == "approve":
            assert value["status"] == "waiting_for_approval", value
            assert value["plan"]["wave"] == 2
            card = next(a for a in value["actions"] if a["tool_name"] == "add_ticket_comment")
            root = next(a for a in value["actions"] if a["key"] == "ticket")
            assert card["arguments"]["ticket_id"] == root["result"]["ticket_id"]
            assert card["approval_status"] == "pending" and card["action_id"] != root["action_id"]
            assert (await counts(admin_engine, run))["ticket_comments"] == 0
            # Fresh service object verifies the wave is restored from checkpoint/ledger.
            await service.close()
            service = RunService(integration_settings)
            await choose(service, run, card, "approve")
            await process_one(service, run)
            value = await service.snapshot(run)
        assert value["status"] == "completed", value
        assert {n["key"]: n["status"] for n in value["plan"]["nodes"]} == expected
        assert value["outcome"] == (
            "rejected"
            if ticket_choice == inbox_choice == "reject"
            else "actions_partially_verified"
        )
        assert value["report"]["verification_status"] != "verified"
        assert {e["key"]: e["status"] for e in value["report"]["effects"]} == expected
        before = await counts(admin_engine, run)
        async with execution_lease(service.engine, run, integration_settings):
            async with TenantSession(service.engine) as session, session.begin():
                plan = await session.scalar(select(RunPlan).where(RunPlan.run_id == run))
                same = await prepare_plan(
                    session, run, MixedPlan.model_validate(plan.document), integration_settings
                )
                assert same.id == plan.id
                original_document = dict(plan.document)
            async with TenantSession(service.engine) as session, session.begin():
                altered = dict(original_document)
                altered["actions"] = [
                    {**a, "arguments": {**a["arguments"], "body": "replan"}}
                    if a["tool"] == "notify_manager"
                    else a
                    for a in altered["actions"]
                ]
                with pytest.raises(Conflict):
                    await prepare_plan(
                        session, run, MixedPlan.model_validate(altered), integration_settings
                    )
        assert await counts(admin_engine, run) == before
    finally:
        await service.close()


async def test_concurrent_decisions_complete_exact_wave_once(integration_settings, admin_engine):
    service, run, value = await pending(
        integration_settings, "Investigate GreenShop and notify manager"
    )
    other = RunService(integration_settings)
    try:
        await asyncio.gather(
            choose(service, run, value["actions"][0], "approve"),
            choose(other, run, value["actions"][1], "approve"),
        )
        await process_one(service, run)
        value = await service.snapshot(run)
        assert value["outcome"] == "actions_verified", value
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 0,
            "notifications": 1,
        }
        for a in value["actions"]:
            await choose(service, run, a, "approve")
        assert not await process_one(service, run)
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 0,
            "notifications": 1,
        }
    finally:
        await service.close()
        await other.close()


async def test_database_verification_reserve_survives_service_restart(integration_settings):
    service, run, value = await pending(integration_settings)
    try:
        action = UUID(value["actions"][0]["action_id"])
        async with execution_lease(service.engine, run, integration_settings):
            await reserve_verification(action)
            await reserve_verification(action)
        await service.close()
        service = RunService(integration_settings)
        async with execution_lease(service.engine, run, integration_settings):
            await reserve_verification(action)
            from opspilot.agent.budgets import BudgetExceeded

            with pytest.raises(BudgetExceeded):
                await reserve_verification(action)
        async with TenantSession(service.engine) as session:
            slot = await session.scalar(select(PlanSlot).where(PlanSlot.action_id == action))
            assert slot.verify_attempts == 3
    finally:
        await service.close()


async def test_real_worker_crash_between_actions_never_replays_completed_intent(
    integration_settings, admin_engine
):
    service, run, value = await pending(
        integration_settings, "Investigate GreenShop and notify manager"
    )
    try:
        for a in value["actions"]:
            await choose(service, run, a, "approve")
        code = """
import asyncio,os
from uuid import UUID
from opspilot.config import Settings
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import tenant_scope
import opspilot.runtime.plans as plans
async def crash(slot):os._exit(99)
plans.after_verified=crash
async def main():
 s=Settings().model_copy(update={'worker_lease_seconds':3,'worker_heartbeat_seconds':1})
 r=RunService(s)
 with tenant_scope(s.local_demo_tenant):await process_one(r,UUID('RUN_ID'))
asyncio.run(main())
""".replace("RUN_ID", str(run))
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(child.communicate(), 30)
        assert child.returncode == 99, stderr.decode()[-200:]
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 0,
            "notifications": 0,
        }
        await service.close()
        service = RunService(integration_settings)
        async with asyncio.timeout(15):
            while True:
                if await process_one(service, run):
                    break
                await asyncio.sleep(0.1)
        value = await service.snapshot(run)
        assert value["outcome"] == "actions_verified", value
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 0,
            "notifications": 1,
        }
    finally:
        await service.close()


async def test_mcp_independently_denies_valid_signed_grant_before_full_wave(
    integration_settings, admin_engine, monkeypatch
):
    from uuid import uuid4

    import jwt

    from opspilot.auth.context import actor_id
    from opspilot.auth.service_context import action_scope
    from opspilot.db.models_workflow import Action, Approval
    from opspilot.mcp_client.client import MCPClient
    from opspilot.runtime.fencing import current_fence
    from opspilot.security.keys import FileGrantKeys
    from opspilot.tenancy.context import require_tenant

    settings = integration_settings
    service, run, value = await pending(settings, "Investigate GreenShop and notify manager")
    try:
        card = next(a for a in value["actions"] if a["key"] == "ticket")
        await choose(service, run, card, "approve")
        async with execution_lease(service.engine, run, settings):
            async with TenantSession(admin_engine) as session, session.begin():
                a = await session.get(Action, UUID(card["action_id"]))
                approval = await session.scalar(select(Approval).where(Approval.action_id == a.id))
                now = await session.scalar(text("SELECT clock_timestamp()"))
                ref, key = FileGrantKeys(
                    settings.service_private_dir, settings.service_public_keys
                ).signing_key(settings.grant_active_kid)
                claims = {
                    "ver": 1,
                    "iss": "urn:opspilot:grant:" + settings.app_env,
                    "aud": "urn:opspilot:execute:" + settings.app_env,
                    "iat": int(now.timestamp()),
                    "nbf": int(now.timestamp()),
                    "exp": int(now.timestamp()) + 30,
                    "jti": str(uuid4()),
                    "tenant": str(require_tenant()),
                    "run": str(run),
                    "revision": str(a.id),
                    "actor": str(actor_id()),
                    "approver": str(approval.decided_by),
                    "payload_hash": a.revision_hash,
                    "epoch": current_fence().epoch,
                    "tool": a.tool_name,
                }
                await session.execute(
                    text("""INSERT INTO workflow.execution_grants
                  (tenant_id,jti,run_id,revision_id,actor_id,approver_id,revision_hash,
                   kid,epoch,issued_at,expires_at)
                  VALUES(:tenant,:jti,:run,:revision,:actor,:approver,:payload_hash,:kid,:epoch,to_timestamp(:iat),to_timestamp(:exp))"""),
                    {**claims, "kid": ref.kid},
                )
                token = jwt.encode(
                    claims,
                    key,
                    algorithm="EdDSA",
                    headers={"kid": ref.kid, "typ": "opspilot-execution+jwt"},
                )

            from opspilot.security.grants import verify

            assert verify(token, settings, now=now)["revision"] == card["action_id"]

            async def supply(*args, **kwargs):
                return token

            monkeypatch.setattr("opspilot.mcp_client.client.issue", supply)
            with action_scope(str(run), card["action_id"], payload_hash(card["arguments"])):
                async with MCPClient(settings).session() as (session, _):
                    result = await MCPClient.call(
                        session,
                        "create_ticket",
                        {
                            "run_id": str(run),
                            "action_id": card["action_id"],
                            "arguments": card["arguments"],
                        },
                    )
            assert not result.ok and result.error.code == "STATE_CONFLICT", result
            assert await counts(admin_engine, run) == {
                "tickets": 0,
                "ticket_comments": 0,
                "notifications": 0,
            }
            async with admin_engine.connect() as conn:
                consumed = await conn.scalar(
                    text("SELECT consumed_at FROM workflow.execution_grants WHERE jti=:j"),
                    {"j": UUID(claims["jti"])},
                )
                assert consumed is None
    finally:
        await service.close()


async def test_next_wave_decision_racing_worker_ack_is_durable(
    integration_settings, admin_engine, monkeypatch
):
    import opspilot.runtime.worker as worker

    original = worker.finish
    service, run, value = await pending(integration_settings)
    entered = asyncio.Event()
    release = asyncio.Event()
    held = False

    async def delayed(engine, job, **kwargs):
        nonlocal held
        if job["run_id"] == run and not held and not kwargs.get("failed"):
            held = True
            entered.set()
            await release.wait()
        await original(engine, job, **kwargs)

    monkeypatch.setattr(worker, "finish", delayed)
    try:
        for a in value["actions"]:
            await choose(service, run, a, "approve")
        active = asyncio.create_task(process_one(service, run))
        await asyncio.wait_for(entered.wait(), 30)
        value = await service.snapshot(run)
        assert value["status"] == "waiting_for_approval" and value["plan"]["wave"] == 2, value
        comment = next(a for a in value["actions"] if a["key"] == "comment")
        await choose(service, run, comment, "approve")
        release.set()
        await asyncio.wait_for(active, 10)
        assert await process_one(service, run)
        value = await service.snapshot(run)
        assert value["outcome"] == "actions_verified", value
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 1,
            "notifications": 1,
        }
    finally:
        release.set()
        await service.close()
