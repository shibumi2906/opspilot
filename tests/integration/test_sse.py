"""Real HTTP/PostgreSQL streaming acceptance; no mocked authorization/event storage."""

import asyncio
import json
import os
import time
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.auth.oidc import digest
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client


async def event(lines):
    async with asyncio.timeout(20):
        fields = {}
        async for line in lines:
            if not line:
                if "event" in fields:
                    return fields
                fields = {}
            elif ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
    raise AssertionError("stream ended")


async def create(client):
    response = await client.post(
        "/api/v2/runs", json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    return response.json()["snapshot_url"]


async def test_snapshot_subscribe_handoff_reconnect_and_scope(integration_settings):
    async with httpx.AsyncClient(
        base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
    ) as client:
        await session_client(client, integration_settings)
        path = await create(client)
        snapshot = (await client.get(path)).json()
        cursor = snapshot["latest_event_id"]
        # Mutation committed after snapshot but before subscribe must be replayed.
        cancel = await client.post(path + "/cancel", json={"command_id": str(uuid4())})
        assert cancel.status_code == 202, cancel.text
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": cursor}
        ) as stream:
            assert stream.status_code == 200
            assert stream.headers["cache-control"] == "no-store"
            assert stream.headers["x-content-type-options"] == "nosniff"
            first = await event(stream.aiter_lines())
            assert first["event"] == "change"
            assert json.loads(first["data"])["sequence"] == snapshot["snapshot_version"] + 1
            cursor = first["id"]
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": cursor}
        ) as stream:
            assert stream.status_code == 200
            # Closing/reopening transport cannot replay a sequence <= cursor.
            line = await anext(stream.aiter_lines())
            assert line == ": heartbeat" or line.startswith("id: ")
        other = await create(client)
        assert (
            await client.get(other + "/events", headers={"Last-Event-ID": cursor})
        ).status_code == 400
        assert (await client.get(path + "/events?token=forbidden")).status_code == 400
        assert (
            await client.get(path + "/events", headers={"Last-Event-ID": cursor + "x"})
        ).status_code == 400
        async with httpx.AsyncClient(
            base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
        ) as foreign:
            await session_client(foreign, integration_settings, tenant=SECOND_TENANT)
            assert (
                await foreign.get(path + "/events", headers={"Last-Event-ID": cursor})
            ).status_code == 404
        await session_client(client, integration_settings)
        assert (
            await client.get(path + "/events", headers={"Last-Event-ID": cursor})
        ).status_code == 400


@pytest.mark.parametrize("mode", ["logout", "expiry", "idle", "disable", "membership", "tenant"])
async def test_stream_revocation_within_30_seconds(integration_settings, admin_engine, mode):
    async with httpx.AsyncClient(
        base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
    ) as client:
        raw, user = await session_client(client, integration_settings)
        path = await create(client)
        snapshot = (await client.get(path)).json()
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": snapshot["latest_event_id"]}
        ) as stream:
            assert stream.status_code == 200
            started = time.monotonic()
            try:
                async with admin_engine.begin() as conn:
                    if mode == "logout":
                        response = await client.post("/auth/logout")
                        assert response.status_code == 200
                    elif mode in {"expiry", "idle"}:
                        field = "expires_at" if mode == "expiry" else "last_seen_at"
                        await conn.execute(
                            text(
                                f"UPDATE identity.sessions SET {field}=clock_timestamp()"
                                "-interval '1 day' WHERE token_hash=:h"
                            ),
                            {"h": digest(raw)},
                        )
                    elif mode == "disable":
                        await conn.execute(
                            text(
                                "UPDATE identity.users SET disabled_at=clock_timestamp() "
                                "WHERE id=:u"
                            ),
                            {"u": user},
                        )
                    elif mode == "membership":
                        await conn.execute(
                            text(
                                "DELETE FROM identity.tenant_memberships "
                                "WHERE user_id=:u AND tenant_id=:t"
                            ),
                            {"u": user, "t": DEMO_TENANT},
                        )
                    else:
                        await conn.execute(
                            text("UPDATE identity.sessions SET tenant_id=:t WHERE token_hash=:h"),
                            {"t": SECOND_TENANT, "h": digest(raw)},
                        )
                lines = stream.aiter_lines()
                while (await event(lines))["event"] != "access_lost":
                    pass
                assert time.monotonic() - started <= 30
            finally:
                async with admin_engine.begin() as conn:
                    await conn.execute(
                        text("UPDATE identity.users SET disabled_at=NULL WHERE id=:u"), {"u": user}
                    )
                    if mode == "membership":
                        # Restore exactly the fixture roles below rather than bypass authorization.
                        for role in ["operator", "approver"]:
                            await conn.execute(
                                text(
                                    "INSERT INTO identity.tenant_memberships"
                                    "(tenant_id,user_id,role) "
                                    "VALUES(:t,:u,:role) ON CONFLICT DO NOTHING"
                                ),
                                {"t": DEMO_TENANT, "u": user, "role": role},
                            )


async def test_actor_capacity_releases_after_disconnect(integration_settings):
    async with httpx.AsyncClient(
        base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
    ) as client:
        await session_client(client, integration_settings)
        path = await create(client)
        async with client.stream("GET", path + "/events") as first:
            assert first.status_code == 200
            async with client.stream("GET", path + "/events") as second:
                assert second.status_code == 200
                third = await client.get(path + "/events")
                assert third.status_code == 429
        await asyncio.sleep(0.2)
        async with client.stream("GET", path + "/events") as released:
            assert released.status_code == 200


async def test_compacted_cursor_reset_then_authoritative_resume(integration_settings, admin_engine):
    async with httpx.AsyncClient(
        base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
    ) as client:
        await session_client(client, integration_settings)
        path = await create(client)
        before = (await client.get(path)).json()
        assert (
            await client.post(path + "/cancel", json={"command_id": str(uuid4())})
        ).status_code == 202
        async with admin_engine.begin() as conn:
            for table in ["event_outbox", "run_audit", "run_events"]:
                await conn.execute(
                    text(f"DELETE FROM workflow.{table} WHERE run_id=:r AND sequence=:s"),
                    {"r": UUID(path.rsplit("/", 1)[1]), "s": before["snapshot_version"] + 1},
                )
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": before["latest_event_id"]}
        ) as stream:
            assert stream.status_code == 200
            assert (await event(stream.aiter_lines()))["event"] == "reset"
        after = (await client.get(path)).json()
        assert after["snapshot_version"] > before["snapshot_version"]
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": after["latest_event_id"]}
        ) as stream:
            assert stream.status_code == 200
            assert await anext(stream.aiter_lines()) == ": heartbeat"


async def test_real_api_process_restart_preserves_cursor(integration_settings):
    import subprocess
    import sys

    def start():
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "opspilot.api.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "18765",
                "--log-level",
                "critical",
                "--no-access-log",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def wait(client):
        async with asyncio.timeout(30):
            while True:
                try:
                    if (await client.get("/health/live")).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)

    process = start()
    try:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:18765", headers={"Accept": "text/event-stream"}
        ) as client:
            await wait(client)
            await session_client(client, integration_settings)
            path = await create(client)
            before = (await client.get(path)).json()
            async with client.stream(
                "GET", path + "/events", headers={"Last-Event-ID": before["latest_event_id"]}
            ) as stream:
                assert stream.status_code == 200
                process.kill()
                await asyncio.to_thread(process.wait)
            process = start()
            await wait(client)
            assert (
                await client.post(path + "/cancel", json={"command_id": str(uuid4())})
            ).status_code == 202
            async with client.stream(
                "GET", path + "/events", headers={"Last-Event-ID": before["latest_event_id"]}
            ) as stream:
                assert stream.status_code == 200
                item = await event(stream.aiter_lines())
                assert json.loads(item["data"])["sequence"] == before["snapshot_version"] + 1
    finally:
        process.kill()
        await asyncio.to_thread(process.wait)


async def test_lost_reservation_disconnects_instead_of_bypassing_capacity(
    integration_settings, admin_engine
):
    from opspilot.api.routes_events import lock_key

    async with httpx.AsyncClient(
        base_url=os.environ["TEST_API_URL"], headers={"Accept": "text/event-stream"}
    ) as client:
        await session_client(client, integration_settings)
        path = await create(client)
        snapshot = (await client.get(path)).json()
        async with client.stream(
            "GET", path + "/events", headers={"Last-Event-ID": snapshot["latest_event_id"]}
        ) as stream:
            assert stream.status_code == 200
            key = lock_key("global", 0)
            async with admin_engine.begin() as conn:
                killed = await conn.scalar(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype='advisory' "
                        "AND classid::bigint=:classid AND objid::bigint=:objid "
                        "AND objsubid=1 AND granted"
                    ),
                    {"classid": (key >> 32) & 0xFFFFFFFF, "objid": key & 0xFFFFFFFF},
                )
                assert killed is True
            started = time.monotonic()
            assert (await event(stream.aiter_lines()))["event"] == "unavailable"
            assert time.monotonic() - started < 10
        async with client.stream("GET", path + "/events") as replacement:
            assert replacement.status_code == 200
