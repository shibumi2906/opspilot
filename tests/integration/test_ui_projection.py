import asyncio
import os
from uuid import UUID

import httpx

from opspilot.contracts.api import CreateRun
from opspilot.llm.scripted import ScriptedProvider
from opspilot.runtime.run_service import RunService


async def test_progress_snapshot_arrives_before_approval(integration_settings, monkeypatch):
    import opspilot.runtime.run_service as module

    original = module.run_investigation
    entered, release = asyncio.Event(), asyncio.Event()

    class PausingProvider(ScriptedProvider):
        async def complete(self, operation, context):
            if operation == "investigate" and not entered.is_set():
                entered.set()
                await release.wait()
            return await super().complete(operation, context)

    async def run(*args, **kwargs):
        return await original(*args, **kwargs, provider=PausingProvider())

    monkeypatch.setattr(module, "run_investigation", run)
    service = RunService(integration_settings)
    try:
        from uuid import uuid4

        created = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        await asyncio.wait_for(entered.wait(), 15)
        snapshot = await service.snapshot(UUID(created["run_id"]))
        assert snapshot["status"] == "running"
        assert {step["node"] for step in snapshot["timeline"]} >= {"classify", "resolve_customer"}
        assert snapshot["evidence"]
        assert snapshot["action"] is None and snapshot["report"] is None
        assert snapshot["usage"]["read_calls"] == 2
    finally:
        release.set()
        await service.close()


async def test_public_config_has_no_secrets(integration_settings):
    async with httpx.AsyncClient() as client:
        response = await client.get(os.environ["TEST_API_URL"] + "/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"mode", "model_id", "synthetic", "scenario_clock", "timezone"}
    assert body["mode"] == "scripted" and body["synthetic"] is True
    assert integration_settings.mcp_service_token.get_secret_value() not in response.text
