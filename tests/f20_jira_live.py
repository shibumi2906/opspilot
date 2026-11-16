"""Authorized KAN smoke through the Full BFF, durable worker and native MCP."""

import asyncio
import hashlib
import json
import os
import re
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.api.main import create_app
from opspilot.auth.context import Principal, auth_scope
from opspilot.auth.service_context import action_scope
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.actions import payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope
from tests.auth_helpers import session_client


def claim_report(report, label):
    with report.open("x") as handle:
        json.dump({"attempt": label, "passed": False, "started": True}, handle)


async def main():
    settings = Settings()
    assert settings.app_env == "test" and settings.llm_mode == "scripted"
    for role in ("migration", "workflow", "domain", "checkpoint", "identity"):
        parsed = make_url(settings.database_url(role))
        assert (parsed.host, parsed.database) == ("postgres", "opspilot_full_test")
    label = os.environ["F20_LIVE_ATTEMPT"]
    assert re.fullmatch(r"[a-z0-9-]{1,60}", label)
    report = Path(f"/reports/live-{label}.json")
    # Never silently rerun a partly completed live test with unknown side effects.
    await asyncio.to_thread(claim_report, report, label)
    # Distinct test content is fixed before normal preparation and approval;
    # earlier unknown operations remain untouched and cannot be redispatched.
    from opspilot.runtime import plans

    original_proposal = plans.canonical_proposal

    def test_proposal(state):
        proposal = original_proposal(state)
        return proposal.model_copy(
            update={
                "title": f"F20 acceptance {label}: " + proposal.title,
                "description": f"F20 acceptance {label}\n" + proposal.description,
            }
        )

    plans.canonical_proposal = test_proposal
    admin = create_engine(settings.database_url("migration"))
    app = create_app(settings)
    service = RunService(settings)
    evidence = {
        "attempt": label,
        "write_destination": "owner-authorized KAN sandbox",
        "passed": False,
    }
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(app.router.lifespan_context(app))
        stack.push_async_callback(admin.dispose)
        stack.push_async_callback(service.close)
        clients = {}
        user = None
        for who in ("operator", "approver"):
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url=settings.app_origin
                )
            )
            _, identity = await session_client(client, settings, who, DEMO_TENANT)
            clients[who] = client
            if who == "operator":
                user = identity

        async def advance(run_id):
            with tenant_scope(DEMO_TENANT):
                assert await process_one(service, run_id), "Expected durable job"
            response = await clients["operator"].get(f"/api/v2/runs/{run_id}")
            assert response.status_code == 200
            return response.json()

        async def create(request):
            response = await clients["operator"].post(
                "/api/v2/runs", json={"request": request, "client_request_id": str(uuid4())}
            )
            assert response.status_code == 202, "Run creation failed"
            run = UUID(response.json()["run_id"])
            value = await advance(run)
            assert value["status"] == "waiting_for_approval", (
                value["status"],
                value.get("error"),
                value.get("outcome"),
            )
            return run, value

        async def decide(run, action, choice):
            body = {
                "action_id": action["action_id"],
                "expected_version": action["expected_version"],
                "decision": choice,
            }
            response = await clients["approver"].post(f"/api/v2/runs/{run}/decision", json=body)
            assert response.status_code in (200, 202), "Decision rejected"
            return body

        rejected, value = await create("Investigate GreenShop in Jira")
        rejected_action = value["action"]
        assert rejected_action["tool_name"] == "create_jira_issue"
        await decide(rejected, rejected_action, "reject")
        final = await advance(rejected)
        assert final["outcome"] == "rejected", final.get("outcome")
        async with admin.connect() as connection:
            count = await connection.scalar(
                text("SELECT count(*) FROM integrations.jira_operations WHERE run_id=:run"),
                {"run": rejected},
            )
            assert count == 0
        evidence["rejected_dispatches"] = 0

        run, value = await create("Investigate GreenShop in Jira and add a comment")
        evidence["run_id"] = str(run)
        await asyncio.to_thread(report.write_text, json.dumps(evidence, indent=2) + "\n")
        issue = value["action"]
        assert issue["arguments"]["site"] == "https://makegrigorev.atlassian.net"
        assert issue["arguments"]["project_id"] == "10001"
        assert issue["tool_name"] == "create_jira_issue"
        body_issue = await decide(run, issue, "approve")
        comment_pending = await advance(run)
        assert comment_pending["status"] == "waiting_for_approval", (
            comment_pending["status"],
            comment_pending.get("outcome"),
            comment_pending.get("error"),
        )
        comment = comment_pending["action"]
        assert comment["tool_name"] == "create_jira_comment"
        assert comment["arguments"]["issue_id"].isdigit()
        body_comment = await decide(run, comment, "approve")
        final = await advance(run)
        assert final["status"] == "completed" and final["outcome"] == "actions_verified", (
            final["status"],
            final.get("outcome"),
            final.get("error"),
        )
        for body in (body_issue, body_comment):
            response = await clients["approver"].post(f"/api/v2/runs/{run}/decision", json=body)
            assert response.status_code == 200, "Decision replay failed"
        assert user is not None
        actor = Principal(user, DEMO_TENANT, frozenset({"operator"}), uuid4(), datetime.now(UTC))
        with auth_scope(actor):
            for action in (issue, comment):
                async with execution_lease(service.engine, run, settings):
                    with action_scope(
                        str(run),
                        action["action_id"],
                        payload_hash(action["arguments"]),
                        tool=action["tool_name"],
                    ):
                        async with MCPClient(settings).session() as (session, _):
                            result = await MCPClient.call(
                                session,
                                action["tool_name"],
                                {
                                    "run_id": str(run),
                                    "action_id": action["action_id"],
                                    "arguments": action["arguments"],
                                },
                            )
                        assert result.ok and result.data["replayed"], "MCP replay failed"
        async with admin.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text("""
                SELECT action_id,outcome,external_id FROM integrations.jira_operations
                WHERE run_id=:run ORDER BY created_at
            """),
                        {"run": run},
                    )
                )
                .mappings()
                .all()
            )
        assert len(rows) == 2 and all(row["outcome"] == "verified" for row in rows)
        evidence.update(
            passed=True,
            issues_created=1,
            comments_created=1,
            verified_receipts=2,
            api_decision_replays=2,
            mcp_replays=2,
            blind_write_retries=0,
            external_id_sha256=[
                hashlib.sha256(row["external_id"].encode()).hexdigest() for row in rows
            ],
            run_id=str(run),
        )
        await asyncio.to_thread(report.write_text, json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence))


if __name__ == "__main__":
    asyncio.run(main())
