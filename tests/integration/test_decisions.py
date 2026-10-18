import asyncio
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.api.main import create_app
from opspilot.contracts.api import CreateRun, Decision
from opspilot.runtime.actions import Conflict, prepare
from opspilot.runtime.run_service import RunService


async def settle(service, run_id):
    async with asyncio.timeout(30):
        while True:
            snapshot = await service.snapshot(run_id)
            if snapshot["status"] not in {"queued", "running"}:
                return snapshot
            await asyncio.sleep(0.02)


@pytest.mark.parametrize("choice,outcome", [("approve", "partial"), ("reject", "rejected")])
async def test_durable_decisions(integration_settings, admin_engine, choice, outcome):
    service = RunService(integration_settings)
    resumes = []
    original_resume = service.resume

    async def counted_resume(run_id, action_id):
        resumes.append((run_id, action_id))
        await original_resume(run_id, action_id)

    service.resume = counted_resume
    async with admin_engine.connect() as conn:
        before = await conn.scalar(text("SELECT count(*) FROM domain.tickets"))
    try:
        body = CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        created = await service.create(body)
        from uuid import UUID

        run_id = UUID(created["run_id"])
        pending = await settle(service, run_id)
        assert pending["status"] == "waiting_for_approval", pending
        assert pending["final_report"] is None
        card = pending["action"]
        async with postgres_checkpointer(integration_settings) as saver:
            saved = await saver.aget_tuple({"configurable": {"thread_id": str(run_id)}})
            assert saved and any(
                task for task in saved.pending_writes if task[1] == "__interrupt__"
            )
        assert (await service.create(body))["run_id"] == str(run_id)
        from opspilot.agent.service import RunConflict

        with pytest.raises(RunConflict):
            await service.create(body.model_copy(update={"request": "Check BlueMarket status"}))
        other = await service.create(
            CreateRun(request="Check GreenShop status", client_request_id=uuid4())
        )
        other_id = UUID(other["run_id"])
        await settle(service, other_id)
        with pytest.raises(Conflict):
            await service.decide(other_id, Decision(action_id=card["action_id"], decision=choice))
        async with AsyncSession(service.engine) as session, session.begin():
            action = await prepare(session, run_id, card["arguments"])
            assert str(action.id) == card["action_id"]
        with pytest.raises(Conflict):
            async with AsyncSession(service.engine) as session, session.begin():
                await prepare(session, run_id, {**card["arguments"], "title": "tampered"})
        decision = Decision(action_id=card["action_id"], decision=choice)
        await asyncio.gather(service.decide(run_id, decision), service.decide(run_id, decision))
        final = await settle(service, run_id)
        assert final["status"] == "completed", final
        assert len(resumes) == 1
        assert final["outcome"] == outcome
        assert final["thread_id"] == str(run_id)
        assert final["action"]["arguments"] == card["arguments"]
        assert final["action"]["arguments_hash"] == card["arguments_hash"]
        assert final["action"]["execution_status"] == "not_started"
        assert final["final_report"]["ticket_id"] is None
        assert ("execute" in final["errors"]) == (choice == "approve")
        await service.decide(run_id, decision)
        with pytest.raises(Conflict):
            await service.decide(
                run_id,
                Decision(
                    action_id=decision.action_id,
                    decision="reject" if choice == "approve" else "approve",
                ),
            )
        with pytest.raises(LookupError):
            await service.decide(run_id, Decision(action_id=uuid4(), decision=choice))
        async with admin_engine.connect() as conn:
            assert await conn.scalar(text("SELECT count(*) FROM domain.tickets")) == before
    finally:
        await service.close()


async def test_api_contract_and_guard(integration_settings):
    import os

    service = RunService(integration_settings)
    other = create_app(integration_settings)
    with pytest.raises(RuntimeError, match="Only one"):
        async with other.router.lifespan_context(other):
            pass
    try:
        async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
            assert (await client.get(f"/api/v1/runs/{uuid4()}")).status_code == 404
            response = await client.post(
                "/api/v1/runs",
                json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
            )
            assert response.status_code == 202
            from uuid import UUID

            run_id = UUID(response.json()["run_id"])
            pending = await settle(service, run_id)
            card = pending["action"]
            path = f"/api/v1/runs/{run_id}/decision"
            body = {"action_id": card["action_id"], "decision": "reject"}
            assert (await client.post(path, json={**body, "arguments": {}})).status_code == 422
            wrong = {**body, "action_id": str(uuid4())}
            assert (await client.post(path, json=wrong)).status_code == 404
            assert (await client.post(path, json=body)).status_code in {200, 202}
            await settle(service, run_id)
            opposite = {**body, "decision": "approve"}
            assert (await client.post(path, json=opposite)).status_code == 409
            public = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert public["action"]["arguments"] == card["arguments"]
            assert "channel_values" not in public and "observations" not in public
            assert integration_settings.mcp_service_token.get_secret_value() not in str(public)
    finally:
        await service.close()


async def test_cli_pause_and_reject(integration_settings):
    import json
    import sys

    async def cli(*arguments):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "opspilot.cli.run",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
        assert process.returncode == 0, stderr.decode()
        return json.loads(stdout)

    pending = await cli("Investigate GreenShop", "--mode", "scripted")
    assert pending["status"] == "waiting_for_approval"
    final = await cli(
        "--run-id", pending["run_id"], "--action-id", pending["action_id"], "--decision", "reject"
    )
    assert final["outcome"] == "rejected"
    assert final["action"]["execution_status"] == "not_started"
    assert final["action"]["arguments"] == pending["proposed_action"]


async def test_background_exception_is_public_failure(integration_settings, monkeypatch):
    from uuid import UUID

    import opspilot.runtime.run_service as module

    original = module.run_investigation

    async def failing(*args, **kwargs):
        if not kwargs.get("queued_only"):
            raise RuntimeError("PRIVATE_INTERNAL_ERROR")
        return await original(*args, **kwargs)

    monkeypatch.setattr(module, "run_investigation", failing)
    service = RunService(integration_settings)
    try:
        created = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        snapshot = await settle(service, UUID(created["run_id"]))
        assert snapshot["status"] == "failed"
        assert snapshot["error"]["code"] == "RUN_FAILED"
        assert "PRIVATE" not in str(snapshot)
    finally:
        await service.close()
