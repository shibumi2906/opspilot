import asyncio
import os
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import pytest
from sqlalchemy import text

from opspilot.auth.context import Principal, auth_scope
from opspilot.auth.service_context import action_scope
from opspilot.cli.bootstrap_identity import SUBJECTS
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.actions import payload_hash
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client


async def ready(client, path):
    async with asyncio.timeout(30):
        while True:
            response = await client.get(path)
            assert response.status_code == 200, response.text
            result = response.json()
            if result["status"] not in {"queued", "running"}:
                return result
            await asyncio.sleep(0.05)


async def make_run(client):
    response = await client.post(
        "/api/v2/runs", json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    path = response.json()["snapshot_url"]
    assert path == "/api/v2/runs/" + response.json()["run_id"]
    return path, await ready(client, path)


@pytest.mark.parametrize("tenant", [DEMO_TENANT, SECOND_TENANT])
async def test_two_tenant_operator_approver_real_mcp_scenario(
    integration_settings, admin_engine, tenant
):
    base = os.environ["TEST_API_URL"]
    async with (
        httpx.AsyncClient(base_url=base) as operator,
        httpx.AsyncClient(base_url=base) as approver,
    ):
        _, owner = await session_client(operator, integration_settings, "operator", tenant)
        await session_client(approver, integration_settings, "approver", tenant)
        path, pending = await make_run(operator)
        assert pending["status"] == "waiting_for_approval", pending
        expected = "00000000-0000-0000-0000-000000000001"
        if tenant == SECOND_TENANT:
            expected = str(uuid5(SECOND_TENANT, expected))
        assert pending["action"]["arguments"]["customer_id"] == expected
        assert (
            await operator.post(
                path + "/decision",
                json={"action_id": pending["action"]["action_id"], "decision": "approve"},
            )
        ).status_code == 403
        accepted = await approver.post(
            path + "/decision",
            json={"action_id": pending["action"]["action_id"], "decision": "approve"},
        )
        assert accepted.status_code == 202, accepted.text
        final = await ready(operator, path)
        assert final["outcome"] == "actions_verified", final
        async with admin_engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT r.actor_id, a.self_approval_exception, t.tenant_id FROM "
                        "workflow.agent_runs r JOIN workflow.actions x ON x.run_id=r.id "
                        "JOIN workflow.approvals a ON a.action_id=x.id JOIN "
                        "domain.tickets t ON t.originating_action_id=x.id WHERE "
                        "r.id=:id"
                    ),
                    {"id": UUID(final["run_id"])},
                )
            ).one()
            assert row == (owner, False, tenant)
        # The same actor's session in the other tenant cannot access this UUID/evidence/count.
        other = SECOND_TENANT if tenant == DEMO_TENANT else DEMO_TENANT
        async with httpx.AsyncClient(base_url=base) as foreign:
            await session_client(foreign, integration_settings, "operator", other)
            assert (
                await foreign.get(path, headers={"X-Tenant-ID": str(tenant)})
            ).status_code == 404
            eid = pending["evidence"][0]["evidence_id"]
            assert (await foreign.get(path + "/evidence/" + eid)).status_code == 404
            history = (await foreign.get("/api/v2/runs")).json()
            assert final["run_id"] not in [r["run_id"] for r in history["items"]]


@pytest.mark.parametrize(
    "name,create_status,history_status,admin_status",
    [
        ("operator", 202, 200, 403),
        ("approver", 403, 200, 403),
        ("auditor", 403, 200, 403),
        ("admin", 403, 403, 200),
        ("unassigned", 403, 403, 403),
    ],
)
async def test_api_role_matrix_and_closed_v1(
    integration_settings, name, create_status, history_status, admin_status
):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        await session_client(client, integration_settings, name)
        response = await client.post(
            "/api/v2/runs",
            json={"request": "Check GreenShop status", "client_request_id": str(uuid4())},
        )
        assert response.status_code == create_status, response.text
        assert (await client.get("/api/v2/runs")).status_code == history_status
        assert (await client.get("/api/v2/runs/" + str(uuid4()))).status_code == 404
        assert (await client.get("/api/v2/admin/memberships")).status_code == admin_status
        assert (await client.get("/api/v1/config")).status_code == 410
        assert (await client.post("/api/v1/runs", json={})).status_code == 410


async def test_history_cursor_actor_filter_admin_scope_and_redaction(
    integration_settings, admin_engine
):
    base = os.environ["TEST_API_URL"]
    async with (
        httpx.AsyncClient(base_url=base) as operator,
        httpx.AsyncClient(base_url=base) as auditor,
        httpx.AsyncClient(base_url=base) as admin,
    ):
        _, owner = await session_client(operator, integration_settings, "operator")
        await session_client(auditor, integration_settings, "auditor")
        _, administrator = await session_client(admin, integration_settings, "admin")
        for _ in range(2):
            response = await operator.post(
                "/api/v2/runs",
                json={"request": "Check GreenShop status", "client_request_id": str(uuid4())},
            )
            await ready(operator, "/api/v2/runs/" + response.json()["run_id"])
        page = (await operator.get("/api/v2/runs?limit=1")).json()
        assert page["total"] >= 2 and page["next_cursor"]
        async with admin_engine.connect() as conn:
            expected = await conn.scalar(
                text("SELECT count(*) FROM workflow.agent_runs WHERE tenant_id=:t AND actor_id=:u"),
                {"t": DEMO_TENANT, "u": owner},
            )
        assert page["total"] == expected
        all_visible = (await operator.get("/api/v2/runs?limit=50")).json()["items"]
        assert all(row["actor_id"] == str(owner) for row in all_visible)

        assert page["items"][0]["actor_id"] == str(owner)
        cursor = page["next_cursor"]
        assert (await auditor.get("/api/v2/runs", params={"cursor": cursor})).status_code == 400
        assert (
            await operator.get("/api/v2/runs", params={"cursor": cursor + "x"})
        ).status_code == 400
        assert (
            await operator.post("/auth/tenant", json={"tenant_id": str(SECOND_TENANT)})
        ).status_code == 200
        assert (await operator.get("/api/v2/runs", params={"cursor": cursor})).status_code == 400
        assert (
            await admin.put(
                "/api/v2/admin/memberships/" + str(administrator),
                json={"roles": ["admin", "approver"]},
            )
        ).status_code == 403
        # An explicit admin mutation affects only its server-selected tenant, not the forged header.
        target = uuid5(
            NAMESPACE_URL, integration_settings.oidc_issuer + "|" + SUBJECTS["unassigned"]
        )
        changed = await admin.put(
            "/api/v2/admin/memberships/" + str(target),
            headers={"X-Tenant-ID": str(SECOND_TENANT)},
            json={"roles": ["auditor"]},
        )
        assert changed.status_code == 200, changed.text
        try:
            async with admin_engine.connect() as conn:
                rows = list(
                    await conn.execute(
                        text(
                            "SELECT tenant_id, role FROM identity.tenant_memberships "
                            "WHERE user_id=:u"
                        ),
                        {"u": target},
                    )
                )
                assert rows == [(DEMO_TENANT, "auditor")]
        finally:
            await admin.put("/api/v2/admin/memberships/" + str(target), json={"roles": []})
        assert (
            await operator.put(
                "/api/v2/admin/memberships/" + str(target), json={"roles": ["admin"]}
            )
        ).status_code == 403
        unauth = httpx.AsyncClient(base_url=base)
        try:
            assert (await unauth.get("/api/v2/runs")).status_code == 401
            assert (await unauth.get("/health")).json() == {"status": "ready"}
        finally:
            await unauth.aclose()


async def test_bearer_only_and_oidc_passthrough_cannot_open_mcp(integration_settings):
    async with httpx.AsyncClient() as client:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "negative", "version": "1"},
            },
        }
        for context in (None, "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJvaWRjIn0.invalid"):
            headers = {
                "Authorization": "Bearer "
                + integration_settings.mcp_service_token.get_secret_value(),
                "Accept": "application/json,text/event-stream",
            }
            if context:
                headers["X-OpsPilot-Context"] = context
            response = await client.post(integration_settings.mcp_url, headers=headers, json=body)
            assert response.status_code == 401


async def test_service_read_context_cannot_write_even_with_persisted_approval(
    integration_settings, admin_engine
):
    base = os.environ["TEST_API_URL"]
    async with (
        httpx.AsyncClient(base_url=base) as operator,
        httpx.AsyncClient(base_url=base) as approver,
    ):
        _, owner = await session_client(operator, integration_settings, "operator")
        _, decider = await session_client(approver, integration_settings, "approver")
        path, pending = await make_run(operator)
        action = UUID(pending["action"]["action_id"])
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE workflow.approvals SET decision='approved', decided_by=:u "
                    "WHERE action_id=:a"
                ),
                {"u": decider, "a": action},
            )
        principal = Principal(owner, DEMO_TENANT, frozenset({"operator"}), uuid4())
        arguments = {
            "run_id": pending["run_id"],
            "action_id": str(action),
            "arguments": pending["action"]["arguments"],
        }
        with auth_scope(principal):
            async with MCPClient(integration_settings).session() as (session, _):
                denied = await MCPClient.call(session, "create_ticket", arguments)
                assert not denied.ok and denied.error.code == "APPROVAL_REQUIRED"
            # Even a correctly signed action context loses authority when the approver is revoked.
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM identity.tenant_memberships WHERE tenant_id=:t AND "
                        "user_id=:u AND role='approver'"
                    ),
                    {"t": DEMO_TENANT, "u": decider},
                )
            try:
                with action_scope(
                    pending["run_id"], str(action), payload_hash(arguments["arguments"])
                ):
                    async with MCPClient(integration_settings).session() as (session, _):
                        denied = await MCPClient.call(session, "create_ticket", arguments)
                        assert not denied.ok and denied.error.code == "APPROVAL_REQUIRED"
            finally:
                async with admin_engine.begin() as conn:
                    await conn.execute(
                        text("INSERT INTO identity.tenant_memberships VALUES (:t,:u,'approver')"),
                        {"t": DEMO_TENANT, "u": decider},
                    )
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                    {"a": action},
                )
                == 0
            )
            assert integration_settings.mcp_service_token.get_secret_value() not in str(pending)


async def test_same_tenant_other_operator_cannot_read_run_or_checkpoint(
    integration_settings, admin_engine
):
    from opspilot.agent.checkpoints import postgres_checkpointer

    base = os.environ["TEST_API_URL"]
    other = uuid5(NAMESPACE_URL, integration_settings.oidc_issuer + "|" + SUBJECTS["unassigned"])
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO identity.tenant_memberships VALUES (:t,:u,'operator')"),
            {"t": DEMO_TENANT, "u": other},
        )
    try:
        async with (
            httpx.AsyncClient(base_url=base) as owner,
            httpx.AsyncClient(base_url=base) as outsider,
        ):
            await session_client(owner, integration_settings, "operator")
            await session_client(outsider, integration_settings, "unassigned")
            path, pending = await make_run(owner)
            forged = await outsider.post(
                "/api/v2/runs",
                json={
                    "request": "Investigate GreenShop",
                    "client_request_id": pending["client_request_id"],
                },
            )
            assert forged.status_code == 409
            assert pending["run_id"] not in forged.text

            for suffix in ("", "/actions", "/evidence/" + pending["evidence"][0]["evidence_id"]):
                assert (await outsider.get(path + suffix)).status_code == 404
            history = (await outsider.get("/api/v2/runs")).json()
            assert history["total"] == 0 and history["items"] == []
            with auth_scope(Principal(other, DEMO_TENANT, frozenset({"operator"}), uuid4())):
                async with postgres_checkpointer(integration_settings) as saver:
                    assert (
                        await saver.aget_tuple({"configurable": {"thread_id": pending["run_id"]}})
                        is None
                    )
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM identity.tenant_memberships WHERE tenant_id=:t AND user_id=:u"),
                {"t": DEMO_TENANT, "u": other},
            )
