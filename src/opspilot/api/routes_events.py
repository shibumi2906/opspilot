"""Bounded, DB-backed SSE with uncached authorization and physical-connection leases."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from opspilot.api.event_cursor import decode, encode
from opspilot.api.routes_runs import get_run
from opspilot.auth.context import AuthError, auth_scope, principal
from opspilot.auth.http import COOKIE, cookie_name


class BoundedStream(StreamingResponse):
    lease: AsyncConnection | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            if self.lease is not None:

                async def release() -> None:
                    assert self.lease is not None
                    await self.lease.invalidate()
                    await self.lease.close()

                await asyncio.shield(release())

    async def stream_response(self, send: Send) -> None:
        async def bounded(message: Any) -> None:
            await asyncio.wait_for(send(message), timeout=3)

        try:
            await super().stream_response(bounded)
        except TimeoutError:
            return


def frame(kind: str, data: dict[str, Any], cursor: str | None = None) -> bytes:
    value = (f"id: {cursor}\n" if cursor else "") + f"event: {kind}\ndata: "
    result = (value + json.dumps(data, separators=(",", ":")) + "\n\n").encode()
    if len(result) > 16384:
        raise ValueError("SSE frame exceeds bound")
    return result


def lock_key(scope: str, slot: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"sse:v1:{scope}:{slot}".encode()).digest()[:8], "big", signed=True
    )


async def events(run_id: UUID, request: Request) -> StreamingResponse:
    if request.url.query or len(request.headers.getlist("last-event-id")) > 1:
        raise AuthError("INVALID_CURSOR", 400)
    original = principal()
    raw = request.cookies.get(cookie_name(request.app.state.identity.settings, COOKIE), "")

    async def authorize() -> dict[str, Any]:
        async with asyncio.timeout(5):
            current = await request.app.state.identity.authenticate(raw)
            if (current.session_id, current.tenant_id, current.user_id) != (
                original.session_id,
                original.tenant_id,
                original.user_id,
            ):
                raise AuthError()
            with auth_scope(current):
                return await get_run(run_id, request)

    snapshot = await authorize()
    supplied = request.headers.get("last-event-id")
    after = decode(request, run_id, supplied) if supplied else 0
    # Advisory locks are server-derived, shared across replicas and released by physical close.
    conn = await asyncio.wait_for(request.app.state.streams_engine.connect(), timeout=5)
    try:
        async with asyncio.timeout(5):
            for scope, count in [
                ("global", 8),
                (f"tenant:{original.tenant_id}", 4),
                (f"actor:{original.user_id}", 2),
            ]:
                for slot in range(count):
                    if await conn.scalar(
                        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key(scope, slot)}
                    ):
                        break
                else:
                    raise AuthError("SSE_CAPACITY", 429)
            await conn.commit()
    except BaseException:
        await conn.invalidate()
        await conn.close()
        raise

    async def check_reservation() -> None:
        # A DB-side disconnect releases advisory locks. Never continue on a replacement lease.
        async with asyncio.timeout(1):
            await conn.execute(text("SELECT 1"))
            await conn.commit()

    async def generate() -> AsyncIterator[bytes]:
        nonlocal after, snapshot
        while True:
            try:
                await check_reservation()
                snapshot = await authorize()
                latest = snapshot["snapshot_version"]
                async with asyncio.timeout(5):
                    async with request.app.state.engine.connect() as db:
                        rows = (
                            (
                                await db.execute(
                                    text(
                                        "SELECT sequence,type,schema_version,"
                                        "snapshot_version,timestamp "
                                        "FROM workflow.run_events WHERE run_id=:r "
                                        "AND tenant_id=:t "
                                        "AND sequence>:s AND sequence<=:latest "
                                        "ORDER BY sequence LIMIT 64"
                                    ),
                                    {
                                        "r": run_id,
                                        "t": original.tenant_id,
                                        "s": after,
                                        "latest": latest,
                                    },
                                )
                            )
                            .mappings()
                            .all()
                        )
                if (
                    after > latest
                    or latest - after > 256
                    or (after < latest and (not rows or rows[0]["sequence"] != after + 1))
                ):
                    yield frame("reset", {"snapshot_url": f"/api/v2/runs/{run_id}"})
                    return
                expected = after + 1
                for row in rows:
                    await check_reservation()
                    await authorize()
                    if row["sequence"] != expected:
                        yield frame("reset", {"snapshot_url": f"/api/v2/runs/{run_id}"})
                        return
                    item = dict(row)
                    item["timestamp"] = item["timestamp"].isoformat()
                    yield frame("change", item, encode(request, run_id, row["sequence"]))
                    after = row["sequence"]
                    expected += 1
                if not rows:
                    yield b": heartbeat\n\n"
                await asyncio.sleep(1)
            except (AuthError, LookupError):
                yield frame("access_lost", {})
                return
            except Exception:
                yield frame("unavailable", {})
                return

    response = BoundedStream(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )

    response.lease = conn
    return response
