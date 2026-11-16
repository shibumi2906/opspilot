"""F20/F21 native MCP + PostgreSQL authorization with a controlled vendor boundary.

Only vendor transport and credential retrieval are replaced. API decisions, signed
service context, manager grants, fencing, RLS and durable receipts remain real.
"""

import asyncio
import copy
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.api.main import create_app
from opspilot.auth.context import Principal, auth_scope
from opspilot.auth.service_context import action_scope
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_server.services import jira
from opspilot.runtime.actions import payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope
from tests.auth_helpers import session_client


@pytest.mark.parametrize("overlay_settings", ["greenshop_expired"], indirect=True)
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "lost_response",
        "denied",
        "rate_limit",
        "read_failure",
        "mismatch",
        "late_duplicate",
        "slow_response",
    ],
)
async def test_jira_native_durable_boundary(overlay_settings, admin_engine, monkeypatch, fault):
    settings = overlay_settings
    # A fresh CI lab has no enrollment or Jira credential. Enroll only a synthetic
    # destination when absent; vendor() below is the sole transport for this test.
    async with admin_engine.begin() as conn:
        present = await conn.scalar(
            text(
                "SELECT count(*) FROM integrations.jira_bindings "
                "WHERE customer_id=:customer AND enabled"
            ),
            {"customer": UUID(int=1)},
        )
        if not present:
            await conn.execute(
                text("""
                INSERT INTO integrations.jira_bindings
                (tenant_id,connector_id,customer_id,version,site,project_id,issue_type_id,addresses,enabled)
                VALUES(:tenant,:connector,:customer,1,'https://synthetic.atlassian.net','1','2','["8.8.8.8"]',true)
            """),
                {"tenant": DEMO_TENANT, "connector": UUID(int=2020), "customer": UUID(int=1)},
            )
    objects = {}
    posts = []
    fail_read = fault == "read_failure"

    async def credential(*args, **kwargs):
        return "Basic controlled-synthetic-credential"

    async def vendor(endpoint, authorization, kind, *, body=None, issue=None, comment=None):
        if kind == "create_issue":
            posts.append(kind)
            if fault == "slow_response":
                await asyncio.sleep(6)
            if fault in {"denied", "rate_limit"}:
                raise ConnectorUnavailable()
            payload = json.loads(body)
            objects["111111"] = {
                "id": "111111",
                "fields": copy.deepcopy(payload["fields"]),
                "marker": payload["properties"][0]["value"],
            }
            if fault == "mismatch":
                objects["111111"]["fields"]["summary"] = "Altered by upstream"
            if fault == "lost_response":
                raise ConnectorUnavailable()
            return {"id": "111111"}
        if kind == "read_issue":
            if fail_read:
                raise ConnectorUnavailable()
            return copy.deepcopy(objects[issue])
        if kind == "issue_marker":
            return {"value": objects[issue]["marker"]}
        if kind == "find_issues":
            return {"isLast": True, "issues": [{"id": i} for i in objects]}
        raise AssertionError("Unexpected vendor route: " + kind)

    monkeypatch.setattr(jira, "call", vendor)
    monkeypatch.setattr(jira, "jira_authorization", credential)
    service = RunService(settings)
    app = create_app(settings)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(service.close)
        await stack.enter_async_context(app.router.lifespan_context(app))
        clients = {}
        user = None
        for who in ("operator", "approver"):
            c = await stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url=settings.app_origin
                )
            )
            _, identity = await session_client(c, settings, who, DEMO_TENANT)
            if who == "operator":
                user = identity
            clients[who] = c
        c = clients["operator"]

        async def create():
            r = await c.post(
                "/api/v2/runs",
                json={
                    "request": "Investigate GreenShop in Jira",
                    "client_request_id": str(uuid4()),
                },
            )
            assert r.status_code == 202
            run = UUID(r.json()["run_id"])
            return run, await step(run)

        async def step(run):
            with tenant_scope(DEMO_TENANT):
                assert await process_one(service, run)
            r = await c.get(f"/api/v2/runs/{run}")
            assert r.status_code == 200
            return r.json()

        async def decision(run, action, choice):
            r = await clients["approver"].post(
                f"/api/v2/runs/{run}/decision",
                json={
                    "action_id": action["action_id"],
                    "expected_version": action["expected_version"],
                    "decision": choice,
                },
            )
            assert r.status_code in (200, 202)

        rejected, v = await create()
        await decision(rejected, v["action"], "reject")
        assert (await step(rejected))["outcome"] == "rejected"
        assert not posts
        run, v = await create()
        action = v["action"]
        assert action["tool_name"] == "create_jira_issue"
        await decision(run, action, "approve")
        final = await step(run)
        assert len(posts) == 1
        async with admin_engine.connect() as conn:
            record = (
                (
                    await conn.execute(
                        text(
                            "SELECT outcome,external_id FROM integrations.jira_operations "
                            "WHERE action_id=:id"
                        ),
                        {"id": UUID(action["action_id"])},
                    )
                )
                .mappings()
                .one()
            )
        if fault in {"none", "late_duplicate", "slow_response"}:
            assert final["outcome"] == "actions_verified"
            assert record["outcome"] == "verified"
        else:
            assert final["outcome"] != "actions_verified"
        if fault == "read_failure":
            # A successful response ID survives a subsequent GET outage.
            assert record["external_id"] == "111111"
            fail_read = False
        if fault == "late_duplicate":
            objects["222222"] = {**copy.deepcopy(objects["111111"]), "id": "222222"}
        response = await c.post(f"/api/v2/jira/operations/{action['action_id']}/reconcile")
        assert response.status_code == 200
        expected = (
            "needs_attention"
            if fault in {"late_duplicate", "mismatch"}
            else "unknown"
            if fault in {"denied", "rate_limit"}
            else "verified"
        )
        assert response.json()["outcome"] == expected
        assert user is not None
        principal = Principal(
            user, DEMO_TENANT, frozenset({"operator"}), uuid4(), datetime.now(UTC)
        )
        with auth_scope(principal):
            async with execution_lease(service.engine, run, settings):
                with action_scope(
                    str(run),
                    action["action_id"],
                    payload_hash(action["arguments"]),
                    tool=action["tool_name"],
                ):
                    async with MCPClient(settings).session() as (session, _):
                        args = {
                            "run_id": str(run),
                            "action_id": action["action_id"],
                            "arguments": action["arguments"],
                        }
                        replay = await MCPClient.call(session, action["tool_name"], args)
                        assert replay.ok == (fault in {"none", "slow_response"})
                        if replay.ok:
                            assert replay.data["replayed"] is True
                        tampered = {
                            **args,
                            "arguments": {**args["arguments"], "project_id": "99999"},
                        }
                        denied = await MCPClient.call(session, action["tool_name"], tampered)
                        assert not denied.ok
        denied = await clients["approver"].post(
            f"/api/v2/jira/operations/{action['action_id']}/reconcile"
        )
        assert denied.status_code == 403
        async with admin_engine.connect() as conn:
            audit = (
                (
                    await conn.execute(
                        text(
                            "SELECT diff FROM workflow.run_audit WHERE action_id=:a "
                            "AND reason_code LIKE 'jira.%' ORDER BY sequence"
                        ),
                        {"a": UUID(action["action_id"])},
                    )
                )
                .scalars()
                .all()
            )
        assert len(audit) >= 1
        assert all(set(row) == {"action_id", "outcome", "external_id_present"} for row in audit)
        # Repeated human decisions cannot enqueue a fresh external operation.
        await decision(run, action, "approve")
        assert len(posts) == 1
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM integrations.jira_operations WHERE action_id=:id"),
                    {"id": UUID(action["action_id"])},
                )
                == 1
            )
