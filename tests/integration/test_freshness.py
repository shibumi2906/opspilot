"""F12 real DB/checkpoint/MCP precondition, replan and clock boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.auth.context import AuthError
from opspilot.runtime.actions import expire_approvals, payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.freshness import reserve_verification
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.security.grants import issue
from opspilot.tenancy.context import DEMO_ACTOR, require_tenant
from tests.integration.test_action_grants import approve, count, rpc
from tests.integration.test_action_grants import pending as single
from tests.integration.test_mixed_plans import choose, counts, pending


async def project(admin, suffix):
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE domain.customer_integrations SET "
                "external_ref=external_ref||:s WHERE tenant_id=:t AND "
                "customer_id='00000000-0000-0000-0000-000000000001'"
            ),
            {"t": require_tenant(), "s": suffix},
        )


async def restore(admin, original):
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE domain.customer_integrations SET external_ref=:v WHERE "
                "tenant_id=:t AND customer_id='00000000-0000-0000-0000-000000000001'"
            ),
            {"t": require_tenant(), "v": original},
        )


async def original_project(admin):
    async with admin.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT external_ref FROM domain.customer_integrations WHERE "
                "tenant_id=:t AND customer_id='00000000-0000-0000-0000-000000000001'"
            ),
            {"t": require_tenant()},
        )


@pytest.mark.parametrize("status", ["healthy", "unknown", "timeout", "stale", "future"])
async def test_fresh_healthy_unknown_never_uses_old_observations(
    integration_settings, admin_engine, monkeypatch, status
):
    from opspilot.mcp_server.adapters import monitoring

    settings = integration_settings
    args = await single(settings)
    await approve(settings, args)
    original = monitoring.observe

    def changed(settings, customer, integration):
        if status == "timeout":
            raise TimeoutError()
        observed = original(settings, customer, integration)
        if status in {"stale", "future"}:
            return {
                **observed,
                "checked_at": settings.scenario_clock
                + timedelta(minutes=-6 if status == "stale" else 1),
            }
        return {**observed, "status": status}

    monkeypatch.setattr(monitoring, "observe", changed)
    service = RunService(settings)
    try:
        assert await process_one(service, args.run_id)
        result = await service.snapshot(args.run_id)
        assert result["status"] == "completed" and result["outcome"] == "partial", result
        assert result["action"]["execution_status"] == "not_started"
        assert await count(admin_engine, args) == 0
    finally:
        await service.close()


@pytest.mark.parametrize("mixed", [False, True])
async def test_project_drift_new_approval_and_run_wide_replan_cap(
    integration_settings, admin_engine, mixed
):
    old_project = await original_project(admin_engine)
    settings = integration_settings
    service, run, value = await pending(
        settings, "Investigate GreenShop and notify manager" if mixed else "Investigate GreenShop"
    )
    try:
        old = value["actions"] if mixed else [value["action"]]
        for a in old:
            await choose(service, run, a, "approve")
        await project(admin_engine, "-new")
        assert await process_one(service, run)
        value = await service.snapshot(run)
        assert value["status"] == "waiting_for_approval", value
        cards = value["actions"] if mixed else [value["action"]]
        changed = next(a for a in cards if a["approval_status"] == "pending")
        assert changed["expected_version"] == 2 and changed["action_id"] not in {
            a["action_id"] for a in old
        }
        assert await counts(admin_engine, run) == {
            "tickets": 0,
            "ticket_comments": 0,
            "notifications": 0,
        }
        # Restart between supersession and new consent; old approval cannot be reused.
        await service.close()
        service = RunService(settings)
        await choose(service, run, changed, "approve")
        await project(admin_engine, "-again")
        assert await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "completed" and final["outcome"] != "actions_verified", final
        assert await counts(admin_engine, run) == {
            "tickets": 0,
            "ticket_comments": 0,
            "notifications": 0,
        }
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT replan_count FROM workflow.agent_runs WHERE id=:r"), {"r": run}
                )
                == 1
            )
    finally:
        await restore(admin_engine, old_project)
        await service.close()


async def test_independent_mcp_rechecks_after_signed_grant(
    integration_settings, admin_engine, monkeypatch
):
    settings = integration_settings
    original = await original_project(admin_engine)
    args = await single(settings)
    await approve(settings, args)
    service = RunService(settings)
    try:
        async with execution_lease(service.engine, args.run_id, settings):
            token = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                },
            )
            await project(admin_engine, "-raced")

            async def saved(*args, **kwargs):
                return token

            monkeypatch.setattr("opspilot.mcp_client.client.issue", saved)
            denied = await rpc(settings, args)
            assert not denied.ok and denied.error.code == "PRECONDITIONS_CHANGED", denied
            assert await count(admin_engine, args) == 0
            async with admin_engine.connect() as conn:
                assert await conn.scalar(
                    text(
                        "SELECT consumed_at IS NULL FROM workflow.execution_grants WHERE "
                        "revision_id=:a"
                    ),
                    {"a": args.action_id},
                )
    finally:
        await restore(admin_engine, original)
        await service.close()


async def test_role_revoked_after_grant_is_denied_in_mcp(
    integration_settings, admin_engine, monkeypatch
):
    settings = integration_settings
    args = await single(settings)
    await approve(settings, args)
    service = RunService(settings)
    try:
        async with execution_lease(service.engine, args.run_id, settings):
            token = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                },
            )
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM identity.tenant_memberships WHERE tenant_id=:t AND "
                        "user_id=:u AND role='approver'"
                    ),
                    {"t": require_tenant(), "u": DEMO_ACTOR},
                )

            async def saved(*args, **kwargs):
                return token

            monkeypatch.setattr("opspilot.mcp_client.client.issue", saved)
            denied = await rpc(settings, args)
            assert not denied.ok and denied.error.code == "APPROVAL_REQUIRED", denied
            assert await count(admin_engine, args) == 0
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.tenant_memberships(tenant_id,user_id,role) "
                    "VALUES(:t,:u,'approver') ON CONFLICT DO NOTHING"
                ),
                {"t": require_tenant(), "u": DEMO_ACTOR},
            )
        await service.close()


async def test_single_verification_budget_is_durable_and_separate(integration_settings):
    from opspilot.agent.budgets import BudgetExceeded

    args = await single(integration_settings)
    service = RunService(integration_settings)
    try:
        for _ in range(3):
            async with execution_lease(service.engine, args.run_id, integration_settings):
                await reserve_verification(args.action_id)
        await service.close()
        service = RunService(integration_settings)
        async with execution_lease(service.engine, args.run_id, integration_settings):
            with pytest.raises(BudgetExceeded):
                await reserve_verification(args.action_id)
    finally:
        await service.close()


async def test_db_ttl_boundary_and_worker_scenario_clock_skew(integration_settings, admin_engine):
    settings = integration_settings.model_copy(
        update={"approval_ttl_seconds": 1, "scenario_clock": datetime(2090, 1, 1, tzinfo=UTC)}
    )
    args = await single(settings)
    service = RunService(settings)
    try:
        # Wait on DB clock, not the worker's synthetic observation clock.
        async with admin_engine.connect() as conn:
            remaining = await conn.scalar(
                text(
                    "SELECT greatest(0,extract(epoch FROM expires_at-clock_timestamp())) "
                    "FROM workflow.approvals WHERE action_id=:a"
                ),
                {"a": args.action_id},
            )
            await conn.execute(text("SELECT pg_sleep(:s)"), {"s": float(remaining)})
        with pytest.raises(AuthError) as exc:
            await approve(settings, args)
        assert exc.value.code == "APPROVAL_EXPIRED"
        await expire_approvals(service)
        await service.close()
        service = RunService(settings)
        await process_one(service, args.run_id)
        assert (await service.snapshot(args.run_id))["action"]["approval_status"] == "expired"
        assert await count(admin_engine, args) == 0
    finally:
        await service.close()


async def test_mixed_replan_preserves_completed_sibling(
    integration_settings, admin_engine, monkeypatch
):
    from opspilot.runtime import plans

    original = await original_project(admin_engine)
    service, run, value = await pending(
        integration_settings, "Investigate GreenShop and notify manager"
    )
    changed = False

    async def after(slot):
        nonlocal changed
        if not changed:
            changed = True
            await project(admin_engine, "-after-ticket")

    monkeypatch.setattr(plans, "after_verified", after)
    try:
        for card in value["actions"]:
            await choose(service, run, card, "approve")
        await process_one(service, run)
        value = await service.snapshot(run)
        assert value["status"] == "waiting_for_approval", value
        assert (await counts(admin_engine, run))["tickets"] == 1
        card = next(a for a in value["actions"] if a["approval_status"] == "pending")
        assert card["key"] == "inbox" and card["expected_version"] == 2
        await choose(service, run, card, "approve")
        await process_one(service, run)
        value = await service.snapshot(run)
        assert value["outcome"] == "actions_verified", value
        assert await counts(admin_engine, run) == {
            "tickets": 1,
            "ticket_comments": 0,
            "notifications": 1,
        }
    finally:
        await restore(admin_engine, original)
        await service.close()


async def test_changed_recipient_needs_own_new_approval(integration_settings, admin_engine):
    from opspilot.db.models_workflow import Action
    from opspilot.runtime.freshness import replace
    from opspilot.tenancy.session import TenantSession

    service, run, value = await pending(
        integration_settings, "Investigate GreenShop and notify manager"
    )
    try:
        old = next(a for a in value["actions"] if a["key"] == "inbox")
        for card in value["actions"]:
            await choose(service, run, card, "approve")
        async with admin_engine.connect() as conn:
            recipient = await conn.scalar(
                text(
                    "SELECT m.user_id FROM identity.tenant_memberships m "
                    "JOIN identity.users u ON u.id=m.user_id WHERE m.tenant_id=:t "
                    "AND m.user_id<>:old AND u.disabled_at IS NULL ORDER BY m.user_id LIMIT 1"
                ),
                {"t": require_tenant(), "old": UUID(old["arguments"]["recipient_id"])},
            )
        async with execution_lease(service.engine, run, integration_settings):
            async with TenantSession(service.engine) as session, session.begin():
                a = await session.get(Action, UUID(old["action_id"]))
                new = await replace(
                    session,
                    a,
                    {**a.arguments, "recipient_id": str(recipient)},
                    integration_settings,
                )
                new_id = new.id
            with pytest.raises((AuthError, DBAPIError)):
                await issue(
                    integration_settings,
                    {
                        "run": str(run),
                        "action": str(new_id),
                        "tool": "notify_manager",
                        "hash": payload_hash({**old["arguments"], "recipient_id": str(recipient)}),
                    },
                )
        await process_one(service, run)
        fresh = await service.snapshot(run)
        assert fresh["status"] == "waiting_for_approval", fresh
        card = next(a for a in fresh["actions"] if a["key"] == "inbox")
        assert card["approval_status"] == "pending" and card["arguments"]["recipient_id"] == str(
            recipient
        )
        assert (await counts(admin_engine, run))["notifications"] == 0
        await choose(service, run, card, "approve")
        await process_one(service, run)
        assert (await service.snapshot(run))["outcome"] == "actions_verified"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT recipient_id FROM domain.notifications "
                        "WHERE originating_action_id=:a"
                    ),
                    {"a": new_id},
                )
                == recipient
            )
    finally:
        await service.close()


async def test_process_crash_after_replan_commit_requires_new_consent(
    integration_settings, admin_engine
):
    import asyncio
    import sys

    original = await original_project(admin_engine)
    settings = integration_settings
    args = await single(settings)
    await approve(settings, args)
    service = RunService(settings)
    try:
        await project(admin_engine, "-crash")
        code = """
import asyncio,os
from uuid import UUID
from opspilot.config import Settings
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import tenant_scope
import opspilot.runtime.freshness as fresh
async def crash(action):os._exit(99)
fresh.after_replanned=crash
async def main():
 s=Settings().model_copy(update={'worker_lease_seconds':3,'worker_heartbeat_seconds':1})
 r=RunService(s)
 with tenant_scope(s.local_demo_tenant):await process_one(r,UUID('RUN_ID'))
asyncio.run(main())
""".replace("RUN_ID", str(args.run_id))
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(child.communicate(), 30)
        assert child.returncode == 99, stderr.decode()[-200:]
        assert await count(admin_engine, args) == 0
        async with asyncio.timeout(15):
            while True:
                if await process_one(service, args.run_id):
                    break
                await asyncio.sleep(0.1)
        fresh = await service.snapshot(args.run_id)
        assert fresh["status"] == "waiting_for_approval", fresh
        assert fresh["action"]["expected_version"] == 2
        assert fresh["action"]["approval_status"] == "pending"
        assert await counts(admin_engine, args.run_id) == {
            "tickets": 0,
            "ticket_comments": 0,
            "notifications": 0,
        }
        await choose(service, args.run_id, fresh["action"], "approve")
        await process_one(service, args.run_id)
        assert (await service.snapshot(args.run_id))["outcome"] == "actions_verified"
        assert (await counts(admin_engine, args.run_id))["tickets"] == 1
    finally:
        await restore(admin_engine, original)
        await service.close()


async def test_replan_cannot_allocate_third_approval_wave(integration_settings, admin_engine):
    original = await original_project(admin_engine)
    service, run, value = await pending(integration_settings)
    try:
        for card in value["actions"]:
            await choose(service, run, card, "approve")
        await project(admin_engine, "-would-require-third-wave")
        await process_one(service, run)
        value = await service.snapshot(run)
        assert value["status"] == "completed" and value["outcome"] != "actions_verified", value
        assert value["replan_count"] == 0
        assert await counts(admin_engine, run) == {
            "tickets": 0,
            "ticket_comments": 0,
            "notifications": 0,
        }
        assert all(card["expected_version"] == 1 for card in value["actions"])
    finally:
        await restore(admin_engine, original)
        await service.close()
