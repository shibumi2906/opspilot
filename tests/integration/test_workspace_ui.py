"""F14 real PostgreSQL/API/MCP access, commands and export boundaries."""

import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.auth.context import auth_scope
from opspilot.auth.store import IdentityStore
from opspilot.db.engine import create_engine
from opspilot.runtime.fencing import execution_lease
from opspilot.tenancy.context import SECOND_TENANT
from tests.auth_helpers import session_client
from tests.integration.test_authorization import make_run
from tests.integration.test_local_operations import BODY, rpc, setup_action


async def test_workspace_inbox_connector_export_scope(integration_settings, admin_engine):
    base = os.environ["TEST_API_URL"]
    async with (
        httpx.AsyncClient(base_url=base) as owner,
        httpx.AsyncClient(base_url=base) as admin,
        httpx.AsyncClient(base_url=base) as auditor,
        httpx.AsyncClient(base_url=base) as foreign,
        httpx.AsyncClient(base_url=base) as peer,
        httpx.AsyncClient(base_url=base) as foreign_admin,
    ):
        raw, _ = await session_client(owner, integration_settings)
        await session_client(admin, integration_settings, "admin")
        await session_client(auditor, integration_settings, "auditor")
        await session_client(foreign, integration_settings, tenant=SECOND_TENANT)
        await session_client(peer, integration_settings, "operator")
        await session_client(foreign_admin, integration_settings, "admin", tenant=SECOND_TENANT)
        store = IdentityStore(integration_settings)
        engine = create_engine(integration_settings.database_url("workflow"))
        try:
            user = await store.authenticate(raw)
            with auth_scope(user):
                args = await setup_action(
                    integration_settings, admin_engine, engine, "notify_manager"
                )
                async with execution_lease(engine, args.run_id, integration_settings):
                    result = await rpc(integration_settings, "notify_manager", args)
                assert result.ok, result
            filtered = await owner.get(
                "/api/v2/runs", params={"customer_id": str(args.arguments.customer_id)}
            )
            assert filtered.status_code == 200, filtered.text
            assert str(args.run_id) in [x["run_id"] for x in filtered.json()["items"]]
            notification = result.data["notification_id"]
            page = await owner.get("/api/v2/inbox?limit=1")
            assert page.status_code == 200, page.text
            assert any(
                str(x["id"]) == notification and x["body"] == BODY for x in page.json()["items"]
            )
            assert notification not in (await foreign.get("/api/v2/inbox")).text
            assert notification not in (await peer.get("/api/v2/inbox")).text
            assert (await owner.get("/api/v2/inbox?cursor=forged")).status_code == 400
            assert (
                await peer.post(
                    f"/api/v2/inbox/{notification}/read", json={"command_id": str(uuid4())}
                )
            ).status_code == 404
            body = {"command_id": str(uuid4())}
            first = await owner.post(f"/api/v2/inbox/{notification}/read", json=body)
            assert first.status_code == 200, first.text
            assert (
                await owner.post(f"/api/v2/inbox/{notification}/read", json=body)
            ).json() == first.json()
            assert (
                await foreign.post(f"/api/v2/inbox/{notification}/read", json=body)
            ).status_code == 404
            exported = await owner.get(f"/api/v2/runs/{args.run_id}/export")
            assert exported.status_code == 200, exported.text
            assert not any(
                k in exported.json() for k in ["request", "evidence", "thread_id", "private_state"]
            )
            assert BODY not in exported.text and len(exported.content) <= 65536
            assert exported.headers["cache-control"] == "no-store"
            assert (await foreign.get(f"/api/v2/runs/{args.run_id}/export")).status_code == 404
            assert (await admin.get(f"/api/v2/runs/{args.run_id}/export")).status_code == 404
            assert (await owner.get("/api/v2/audit")).status_code == 403
            audit = await auditor.get("/api/v2/audit?limit=1")
            assert audit.status_code == 200, audit.text
            assert not {"diff", "payload", "private_state"} & audit.json()["items"][0].keys()
            if audit.json()["next_cursor"]:
                assert (
                    await foreign.get(
                        "/api/v2/audit", params={"cursor": audit.json()["next_cursor"]}
                    )
                ).status_code == 403
            connections = (await admin.get("/api/v2/admin/connectors")).json()["items"]
            target = next(
                x for x in connections if x["customer_id"] == str(args.arguments.customer_id)
            )
            assert "external_ref" not in target
            assert (await owner.get("/api/v2/admin/connectors")).status_code == 403
            command = {
                "command_id": str(uuid4()),
                "expected_version": target["version"],
                "enabled": False,
            }
            assert (
                await foreign_admin.put("/api/v2/admin/connectors/" + target["id"], json=command)
            ).status_code == 404
            disabled = await admin.put("/api/v2/admin/connectors/" + target["id"], json=command)
            assert disabled.status_code == 200, disabled.text
            try:
                assert (
                    await admin.put("/api/v2/admin/connectors/" + target["id"], json=command)
                ).json() == disabled.json()
                conflict = {**command, "enabled": True}
                assert (
                    await admin.put("/api/v2/admin/connectors/" + target["id"], json=conflict)
                ).status_code == 409
                assert (
                    await foreign.put("/api/v2/admin/connectors/" + target["id"], json=command)
                ).status_code == 403
                with auth_scope(user):
                    async with engine.begin() as conn:
                        value = await conn.scalar(
                            text("SELECT workflow.precondition_snapshot(:r,CAST(:a AS jsonb))"),
                            {"r": args.run_id, "a": args.arguments.model_dump_json()},
                        )
                        assert value is None
            finally:
                restored = await admin.put(
                    "/api/v2/admin/connectors/" + target["id"],
                    json={
                        "command_id": str(uuid4()),
                        "expected_version": disabled.json()["version"],
                        "enabled": True,
                    },
                )
                assert restored.status_code == 200, restored.text
            with auth_scope(user):
                async with engine.begin() as conn:
                    value = await conn.scalar(
                        text("SELECT workflow.precondition_snapshot(:r,CAST(:a AS jsonb))"),
                        {"r": args.run_id, "a": args.arguments.model_dump_json()},
                    )
                    assert any(
                        x.get("control_version") == restored.json()["version"]
                        for x in value["integrations"]
                    )
        finally:
            await engine.dispose()
            await store.engine.dispose()


async def test_history_filter_cursor_and_membership_cas(integration_settings):
    async with (
        httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as owner,
        httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as admin,
    ):
        await session_client(owner, integration_settings)
        _, administrator = await session_client(admin, integration_settings, "admin")
        path, _ = await make_run(owner)
        result = await owner.get("/api/v2/runs", params={"q": "Investigate GreenShop", "limit": 1})
        assert result.status_code == 200, result.text
        assert result.json()["items"] and "GreenShop" in result.json()["items"][0]["request"]
        if result.json()["next_cursor"]:
            assert (
                await owner.get(
                    "/api/v2/runs", params={"q": "changed", "cursor": result.json()["next_cursor"]}
                )
            ).status_code == 400
        assert (await owner.get("/api/v2/runs?since=2026-01-01")).status_code == 400
        assert (await owner.get("/api/v2/runs?q=%25_%27")).status_code == 200
        assert (
            await admin.put(
                "/api/v2/admin/memberships/" + str(administrator),
                json={"roles": [], "expected_roles": ["admin"]},
            )
        ).status_code == 409
        assert (
            await admin.put(
                "/api/v2/admin/memberships/" + str(administrator),
                json={"roles": ["admin"], "expected_roles": []},
            )
        ).status_code == 409
        export = await owner.get(path + "/export")
        assert export.status_code == 200
        assert "request" not in json.loads(export.content)


@pytest.mark.parametrize("path", ["/api/v2/inbox", "/api/v2/audit", "/api/v2/admin/connectors"])
async def test_private_workspace_requires_session(integration_settings, path):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await client.get(path)).status_code == 401
