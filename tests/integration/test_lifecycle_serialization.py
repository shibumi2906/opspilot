"""Eligibility is evaluated only after runtime transactions have drained."""

import asyncio

from sqlalchemy import text

from opspilot.db.engine import create_engine
from opspilot.security.lifecycle import RetentionPolicy, retain
from opspilot.tenancy.context import DEMO_TENANT
from tests.integration.test_lifecycle import administrator
from tests.integration.test_local_operations import setup_action


async def test_compaction_waits_for_runtime_and_observes_new_unknown(
    integration_settings, admin_engine
):
    runtime = create_engine(integration_settings.database_url("workflow"))
    task = None
    try:
        args = await setup_action(integration_settings, admin_engine, runtime, "create_ticket")
        async with admin_engine.begin() as conn:
            actor = await administrator(conn)
            await conn.execute(
                text(
                    "UPDATE workflow.agent_runs SET status='completed',"
                    "updated_at=clock_timestamp()-interval '400 days' WHERE id=:r"
                ),
                {"r": args.run_id},
            )
        entered = asyncio.Event()
        backend = []

        async def preview():
            async with admin_engine.begin() as conn:
                backend.append(await conn.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await retain(conn, DEMO_TENANT, actor, RetentionPolicy())

        async with runtime.begin() as reader:
            await reader.execute(text("SELECT 1"))
            task = asyncio.create_task(preview())
            await entered.wait()
            # Observe a real blocked exclusive maintenance request, not a sleep-only assertion.
            async with admin_engine.connect() as observer:
                for _ in range(50):
                    if await observer.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:p "
                            "AND locktype='advisory' AND mode='ExclusiveLock' AND NOT granted)"
                        ),
                        {"p": backend[0]},
                    ):
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("Compaction crossed an active runtime transaction")
            async with admin_engine.begin() as writer:
                await writer.execute(
                    text("UPDATE workflow.actions SET execution_status='unknown' WHERE id=:a"),
                    {"a": args.action_id},
                )
        result = await task
        assert str(args.run_id) not in {r["run_id"] for r in result["runs"]}
        async with admin_engine.connect() as conn:
            assert not await conn.scalar(
                text("SELECT EXISTS(SELECT 1 FROM workflow.deletion_tombstones WHERE run_id=:r)"),
                {"r": args.run_id},
            )
    finally:
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.dispose()
