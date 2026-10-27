"""Real DB atomicity, durable replay, projection recovery and object authorization."""

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.contracts.api import CreateRun, Decision
from opspilot.db.engine import create_engine
from opspilot.runtime.events import publish_pending
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.recovery import recover
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import SECOND_TENANT, tenant_scope
from tests.auth_helpers import session_client
from tests.integration.test_authorization import make_run


async def counts(engine, run):
    async with engine.connect() as conn:
        return tuple(
            [
                await conn.scalar(
                    text(f"SELECT count(*) FROM workflow.{table} WHERE run_id=:r"), {"r": run}
                )
                for table in ("run_events", "run_audit", "event_outbox")
            ]
        )


async def test_atomic_state_event_audit_outbox_rollback(
    integration_settings, admin_engine, monkeypatch
):
    import opspilot.agent.service as creator

    service = RunService(integration_settings)
    body = CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
    original = creator.enqueue

    async def fail(session, run, *args):
        assert await counts(admin_engine, run) == (0, 0, 0)  # uncommitted trigger rows invisible
        raise RuntimeError("crash before commit")

    try:
        monkeypatch.setattr(creator, "enqueue", fail)
        with pytest.raises(RuntimeError):
            await service.create(body)
        monkeypatch.setattr(creator, "enqueue", original)
        run = UUID((await service.create(body))["run_id"])
        assert await counts(admin_engine, run) == (1, 1, 1)
        await service.create(body)
        assert await counts(admin_engine, run) == (1, 1, 1)
        async with execution_lease(service.engine, run, integration_settings):
            before = await counts(admin_engine, run)
            with pytest.raises(RuntimeError):
                async with service.engine.begin() as conn:
                    await conn.execute(
                        text("UPDATE workflow.agent_runs SET status='failed' WHERE id=:r"),
                        {"r": run},
                    )
                    raise RuntimeError("crash after state/event writes")
            assert await counts(admin_engine, run) == before
        assert (await service.snapshot(run))["status"] == "queued"
    finally:
        await service.close()


async def test_concurrent_sequence_and_duplicate_out_of_order_delivery(
    integration_settings, admin_engine
):
    service = RunService(integration_settings)
    run = UUID(
        (
            await service.create(
                CreateRun(request="Check GreenShop status", client_request_id=uuid4())
            )
        )["run_id"]
    )
    try:
        async with execution_lease(service.engine, run, integration_settings):

            async def append():
                async with service.engine.begin() as conn:
                    await conn.execute(text("SELECT workflow.record_recovery(:r)"), {"r": run})

            await asyncio.gather(*(append() for _ in range(12)))
        async with service.engine.connect() as conn:
            sequences = (
                (
                    await conn.execute(
                        text(
                            "SELECT sequence FROM workflow.run_events WHERE run_id=:r ORD"
                            "ER BY sequence"
                        ),
                        {"r": run},
                    )
                )
                .scalars()
                .all()
            )
        assert sequences == list(range(1, 14))
        assert await counts(admin_engine, run) == (13, 13, 13)
        # Publication was never called before this point: a worker crash loses nothing.
        async with service.engine.begin() as conn:
            for n in (13, 1, 13, 4, 2):
                await conn.execute(text("SELECT workflow.publish_event(:r,:s)"), {"r": run, "s": n})
        while await publish_pending(service.engine):
            pass
        async with service.engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT sequence FROM workflow.event_delivery WHERE run_id=:r"), {"r": run}
                )
                == 13
            )
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.event_outbox WHERE run_id=:r A"
                        "ND published_at IS NULL"
                    ),
                    {"r": run},
                )
                == 0
            )
        assert (await service.snapshot(run))["snapshot_version"] == 13
        assert (await service.snapshot(run))["status"] == "queued"
    finally:
        await service.close()


async def test_receipt_recovery_projection_and_audit_explain_run(
    integration_settings, admin_engine
):
    service = RunService(integration_settings)
    try:
        run = UUID(
            (
                await service.create(
                    CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
                )
            )["run_id"]
        )
        await process_one(service, run)
        pending = await service.snapshot(run)
        await recover(service, run)
        await service.decide(
            run,
            Decision(
                expected_version=1, action_id=pending["action"]["action_id"], decision="approve"
            ),
        )
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["action"]["result"]["ticket_id"]
        # Destroy only the old disposable cache, preserving authoritative stream projection/receipt.
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE workflow.agent_runs DISABLE TRIGGER transactional_event")
            )
            await conn.execute(
                text("UPDATE workflow.agent_runs SET public_snapshot='{}' WHERE id=:r"), {"r": run}
            )
            await conn.execute(
                text("ALTER TABLE workflow.agent_runs ENABLE TRIGGER transactional_event")
            )
        restored = await service.snapshot(run)
        assert restored["report"] == final["report"]
        assert restored["timeline"] == final["timeline"]
        assert restored["action"]["result"] == final["action"]["result"]
        assert restored["snapshot_version"] == final["snapshot_version"]
        async with service.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT e.type,a.reason_code,a.execution_epoch FROM workflow."
                        "run_events e JOIN workflow.run_audit a USING(tenant_id,run_i"
                        "d,sequence) WHERE e.run_id=:r ORDER BY sequence"
                    ),
                    {"r": run},
                )
            ).all()
        types = [r.type for r in rows]
        assert {
            "run.created",
            "approval.requested",
            "approval.decided",
            "operation.receipt_recorded",
            "recovery.started",
        } <= set(types)
        assert types.count("operation.receipt_recorded") == 1
        assert all(r.reason_code for r in rows)
        assert next(r.execution_epoch for r in rows if r.type == "recovery.started") > 0
    finally:
        await service.close()


@pytest.mark.parametrize(
    "table", ["run_events", "run_audit", "run_streams", "event_outbox", "event_delivery"]
)
async def test_runtime_cannot_mutate_event_storage(integration_settings, table):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        for operation in ("UPDATE", "DELETE"):
            with pytest.raises(DBAPIError):
                async with engine.begin() as conn:
                    query = (
                        f"UPDATE workflow.{table} SET sequence=0"
                        if operation == "UPDATE"
                        else f"DELETE FROM workflow.{table}"
                    )
                    await conn.execute(text(query))
    finally:
        await engine.dispose()


async def test_replay_authorization_bound_cursors_and_private_state(
    integration_settings, admin_engine
):
    base = os.environ["TEST_API_URL"]
    async with (
        httpx.AsyncClient(base_url=base) as owner,
        httpx.AsyncClient(base_url=base) as foreign,
        httpx.AsyncClient(base_url=base) as auditor,
    ):
        await session_client(owner, integration_settings, "operator")
        await session_client(foreign, integration_settings, "operator", SECOND_TENANT)
        await session_client(auditor, integration_settings, "auditor")
        path, pending = await make_run(owner)
        run = UUID(pending["run_id"])
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE workflow.run_streams SET projection=projection || CAS"
                    "T(:p AS jsonb) WHERE run_id=:r"
                ),
                {
                    "r": run,
                    "p": '{"private_state":"F07_SECRET_SENTINEL","thread_id":"F07_SECR'
                    'ET_SENTINEL","observations":{"token":"F07_SECRET_SENTINEL"}}',
                },
            )
        snap = await owner.get(path)
        assert snap.status_code == 200
        assert "F07_SECRET_SENTINEL" not in snap.text
        assert (
            not {"budget", "thread_id", "trace_context", "observations", "tool_results"}
            & snap.json().keys()
        )
        for stream in ("events", "audit"):
            response = await owner.get(path + "/" + stream, params={"limit": 1})
            assert response.status_code == 200, response.text
            page = response.json()
            assert page["schema_version"] == 1 and len(page["items"]) == 1
            cursor = page["next_cursor"]
            assert cursor and page["items"][0]["sequence"] == 1
            assert "F07_SECRET_SENTINEL" not in response.text
            assert (
                await foreign.get(path + "/" + stream, params={"cursor": cursor})
            ).status_code == 404
            assert (
                await auditor.get(path + "/" + stream, params={"cursor": cursor})
            ).status_code == 400
            other_stream = "audit" if stream == "events" else "events"
            assert (
                await owner.get(path + "/" + other_stream, params={"cursor": cursor})
            ).status_code == 400
            another, _ = await make_run(owner)
            assert (
                await owner.get(another + "/" + stream, params={"cursor": cursor})
            ).status_code == 400
            assert (await owner.get(path + "/" + stream, params={"limit": 101})).status_code == 422
            second = (
                await owner.get(path + "/" + stream, params={"cursor": cursor, "limit": 1})
            ).json()
            assert second["items"][0]["sequence"] == 2
        engine = create_engine(integration_settings.database_url("workflow"))
        try:
            with tenant_scope(SECOND_TENANT):
                async with engine.connect() as conn:
                    assert (
                        await conn.scalar(
                            text("SELECT count(*) FROM workflow.run_events WHERE run_id=:r"),
                            {"r": run},
                        )
                        == 0
                    )
        finally:
            await engine.dispose()


async def test_committed_create_survives_process_death_before_publication(
    integration_settings, admin_engine
):
    import sys

    code = """
import asyncio, os
from uuid import uuid4
from opspilot.config import Settings
from opspilot.contracts.api import CreateRun
from opspilot.runtime.run_service import RunService
from opspilot.tenancy.context import tenant_scope
async def main():
    settings=Settings()
    with tenant_scope(settings.local_demo_tenant):
        service=RunService(settings)
        body=CreateRun(request='Check GreenShop status',client_request_id=uuid4())
        created=await service.create(body)
        print(created['run_id'],flush=True)
        os._exit(73)
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await asyncio.wait_for(process.communicate(), 60)
    assert process.returncode == 73
    run = UUID(stdout.decode().strip())
    assert await counts(admin_engine, run) == (1, 1, 1)
    service = RunService(integration_settings)
    try:
        assert (await service.snapshot(run))["status"] == "queued"
        while await publish_pending(service.engine):
            pass
        async with service.engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT published_at IS NOT NULL FROM workflow.event_outbox WHERE run_id=:r"),
                {"r": run},
            )
    finally:
        await service.close()


async def test_bounded_history_reset_and_stale_fence(integration_settings, admin_engine):
    from opspilot.runtime.fencing import current_fence

    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as owner:
        await session_client(owner, integration_settings, "operator")
        path, pending = await make_run(owner)
        run = UUID(pending["run_id"])
        first = (await owner.get(path + "/events", params={"limit": 1})).json()["next_cursor"]
        service = RunService(integration_settings)
        try:
            # Allocation in one transaction is enough to exercise the bounded replay window.
            async with execution_lease(service.engine, run, integration_settings):
                fence = current_fence()
                async with service.engine.begin() as conn:
                    await conn.execute(
                        text("SELECT workflow.record_recovery(:r) FROM generate_series(1,1001)"),
                        {"r": run},
                    )
                async with admin_engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE workflow.run_execution_leases SET epoch=epoch+1 WHERE run_id=:r"
                        ),
                        {"r": run},
                    )
                assert fence is not None
                before = await counts(admin_engine, run)
                with pytest.raises(DBAPIError):
                    async with service.engine.begin() as conn:
                        await conn.execute(text("SELECT workflow.record_recovery(:r)"), {"r": run})
                assert await counts(admin_engine, run) == before
            for stream in ("events", "audit"):
                page = (await owner.get(path + "/" + stream, params={"limit": 100})).json()
                assert page["reset_required"]
                assert page["earliest_sequence"] == page["snapshot_version"] - 999
                assert page["items"][0]["sequence"] == page["earliest_sequence"]
                assert len(page["items"]) == 100
            reset = (await owner.get(path + "/events", params={"cursor": first})).json()
            assert reset["reset_required"]
        finally:
            await service.close()
