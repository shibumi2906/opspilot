import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from opspilot.contracts.api import CreateRun, Decision
from opspilot.contracts.common import ToolError, ToolResult
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.run_service import RunService


async def settle(service, run_id):
    async with asyncio.timeout(30):
        while True:
            value = await service.snapshot(run_id)
            if value["status"] not in {"running", "queued"}:
                return value
            await asyncio.sleep(0.02)


@pytest.mark.parametrize(
    "fault,outcome,verification,ticket_count",
    [
        ("lost_response", "actions_verified", "verified", 1),
        ("write_unavailable", "unknown_outcome", "not_started", 0),
        ("mismatch", "partial", "mismatch", 1),
        ("missing_ticket", "unknown_outcome", "unknown", 1),
        ("verify_reserve", "actions_verified", "verified", 1),
    ],
)
async def test_execution_faults_and_verification(
    integration_settings,
    admin_engine,
    monkeypatch,
    fault,
    outcome,
    verification,
    ticket_count,
):
    settings = integration_settings.model_copy(update={"agent_max_reads": 8})
    service = RunService(settings)
    original_call = MCPClient.call
    writes = []

    async def call(session, name, arguments):
        if name == "create_ticket":
            writes.append(arguments)
            if fault == "write_unavailable":
                raise TimeoutError("PRIVATE_TRANSPORT_DETAILS")
        if name == "get_ticket" and fault == "missing_ticket":
            return ToolResult(
                ok=False,
                observed_at=settings.scenario_clock,
                error=ToolError(code="NOT_FOUND", message="Ticket not found"),
            )
        result = await original_call(session, name, arguments)
        if name == "create_ticket" and fault == "lost_response":
            assert result.ok
            raise TimeoutError("Response lost after commit")
        if name == "get_ticket" and fault == "mismatch":
            return result.model_copy(update={"data": {**result.data, "title": "unexpected title"}})
        return result

    monkeypatch.setattr(MCPClient, "call", staticmethod(call))
    try:
        created = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        run_id = UUID(created["run_id"])
        pending = await settle(service, run_id)
        assert pending["status"] == "waiting_for_approval", pending
        action = pending["action"]
        decision = Decision(action_id=action["action_id"], decision="approve")
        await service.decide(run_id, decision)
        final = await settle(service, run_id)
        assert final["outcome"] == outcome, final
        assert final["final_report"]["verification_status"] == verification
        assert len(writes) == 1
        assert writes[0]["arguments"] == action["arguments"]
        assert "PRIVATE" not in str(final)
        if fault == "verify_reserve":
            assert final["budget"]["read_attempts"] == 8
        if outcome == "unknown_outcome" and ticket_count == 0:
            assert final["action"]["execution_status"] == "unknown"
            assert final["report"]["ticket_id"] is None
            assert "unknown" in final["report"]["action_summary"]
        await service.decide(run_id, decision)
        assert len(writes) == 1
        async with admin_engine.connect() as conn:
            count = await conn.scalar(
                text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:id"),
                {"id": UUID(action["action_id"])},
            )
            assert count == ticket_count
    finally:
        await service.close()
