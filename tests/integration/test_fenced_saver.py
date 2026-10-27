from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import text

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.contracts.api import CreateRun
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one


async def test_sdk_checkpoint_and_pending_writes_rollback_atomically(
    integration_settings, admin_engine
):
    service = RunService(integration_settings)
    result = await service.create(
        CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
    )
    run = UUID(result["run_id"])
    ns = "atomic-f06-" + str(uuid4())
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("""CREATE OR REPLACE FUNCTION checkpoints.f06_injected_failure()
          RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.checkpoint_ns LIKE 'atomic-f06-%' AND (TG_TABLE_NAME='checkpoints'
            OR to_jsonb(NEW)->>'channel'='reject-f06') THEN
            RAISE EXCEPTION 'INJECTED_SDK_ROLLBACK' USING ERRCODE='23514';
          END IF; RETURN NEW; END $$""")
        )
        for table in ("checkpoints", "checkpoint_writes"):
            await conn.execute(
                text(
                    f"CREATE TRIGGER f06_failure BEFORE INSERT ON checkpoints.{table} "
                    "FOR EACH ROW EXECUTE FUNCTION checkpoints.f06_injected_failure()"
                )
            )
    try:
        async with execution_lease(service.engine, run, integration_settings):
            async with postgres_checkpointer(integration_settings) as saver:
                cp = empty_checkpoint()
                cp["channel_values"] = {"payload": {"value": "must roll back"}}
                config = {
                    "configurable": {
                        "thread_id": str(run),
                        "checkpoint_ns": ns,
                        "checkpoint_id": cp["id"],
                    }
                }
                with pytest.raises(Exception) as checkpoint_error:
                    await saver.aput(
                        config, cp, {"source": "update", "step": 0, "parents": {}}, {"payload": "1"}
                    )
                assert checkpoint_error.value.sqlstate == "23514"
                with pytest.raises(Exception) as writes_error:
                    await saver.aput_writes(
                        config, [("keep-f06", 1), ("reject-f06", 2)], str(uuid4())
                    )
                assert writes_error.value.sqlstate == "23514"
        async with admin_engine.connect() as conn:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                assert (
                    await conn.scalar(
                        text(f"SELECT count(*) FROM checkpoints.{table} WHERE checkpoint_ns=:ns"),
                        {"ns": ns},
                    )
                    == 0
                )
    finally:
        async with admin_engine.begin() as conn:
            for table in ("checkpoints", "checkpoint_writes"):
                await conn.execute(
                    text(f"DROP TRIGGER IF EXISTS f06_failure ON checkpoints.{table}")
                )
            await conn.execute(text("DROP FUNCTION checkpoints.f06_injected_failure()"))
        await service.close()


async def test_pinned_workflow_mismatch_never_invokes_graph(integration_settings, admin_engine):
    service = RunService(integration_settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE workflow.agent_runs SET workflow_version='unsupported-future' "
                    "WHERE id=:r"
                ),
                {"r": run},
            )
        await process_one(service, run)
        snapshot = await service.snapshot(run)
        assert snapshot["status"] == "needs_attention"
        assert snapshot["error"]["code"] == "UNSUPPORTED_WORKFLOW_VERSION"
        assert snapshot["action"] is None
    finally:
        await service.close()


async def test_corrupt_checkpoint_binding_blocks_local_dispatch(integration_settings, admin_engine):
    from opspilot.contracts.api import Decision

    service = RunService(integration_settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        await process_one(service, run)
        pending = await service.snapshot(run)
        assert pending["status"] == "waiting_for_approval"
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("""UPDATE checkpoints.checkpoints SET checkpoint=jsonb_set(
              checkpoint,'{channel_values,run_id}',to_jsonb(CAST(:wrong AS text)))
              WHERE thread_id=:r"""),
                {"r": str(run), "wrong": str(uuid4())},
            )
        await service.decide(
            run, Decision(action_id=pending["action"]["action_id"], decision="approve")
        )
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "needs_attention"
        assert final["error"]["code"] == "CHECKPOINT_UNSUPPORTED"
        assert final["action"]["execution_status"] == "not_started"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                    {"a": UUID(pending["action"]["action_id"])},
                )
                == 0
            )
    finally:
        await service.close()


async def test_blocked_heartbeat_cannot_revive_expired_lease(integration_settings, admin_engine):
    import asyncio

    from opspilot.runtime.fencing import acquire, heartbeat, release

    service = RunService(integration_settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        async with service.engine.begin() as conn:
            fence = await acquire(conn, run, uuid4(), 1.0)
        assert fence is not None
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("SELECT epoch FROM workflow.run_execution_leases WHERE run_id=:r FOR UPDATE"),
                {"r": run},
            )
            renewal = asyncio.create_task(heartbeat(service.engine, fence, 3))
            await asyncio.sleep(1.3)
            assert not renewal.done()
        assert await asyncio.wait_for(renewal, 5) is False
        await release(service.engine, fence)
    finally:
        await service.close()


async def test_old_epoch_is_rejected_even_when_owner_id_is_reused(integration_settings):
    from opspilot.runtime.fencing import acquire, fence_scope, heartbeat, release

    service = RunService(integration_settings)
    try:
        result = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run = UUID(result["run_id"])
        owner = uuid4()
        async with service.engine.begin() as conn:
            old = await acquire(conn, run, owner, 30)
        assert old is not None
        await release(service.engine, old)
        async with service.engine.begin() as conn:
            current = await acquire(conn, run, owner, 30)
        assert current is not None and current.epoch > old.epoch
        assert not await heartbeat(service.engine, old, 3)
        with fence_scope(old):
            with pytest.raises(Exception) as rejected:
                async with service.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE workflow.agent_runs SET "
                            "public_snapshot=jsonb_build_object('late',true) WHERE id=:r"
                        ),
                        {"r": run},
                    )
            assert rejected.value.orig.sqlstate == "40001"
        with fence_scope(current):
            async with service.engine.begin() as conn:
                await conn.execute(text("SELECT workflow.check_fence(:r)"), {"r": run})
        await release(service.engine, current)
        assert "late" not in await service.snapshot(run)
    finally:
        await service.close()
