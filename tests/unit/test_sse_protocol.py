import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from opspilot.api.event_cursor import decode, encode
from opspilot.api.routes_events import BoundedStream, frame, lock_key
from opspilot.auth.context import AuthError, Principal, auth_scope


def test_cursor_binds_session_actor_tenant_run_and_bounds():
    settings = SimpleNamespace(session_signing_key=SecretStr("k" * 64))
    app = SimpleNamespace(state=SimpleNamespace(identity=SimpleNamespace(settings=settings)))
    request = Request({"type": "http", "app": app})
    user = Principal(uuid4(), uuid4(), frozenset({"operator"}), uuid4())
    run = uuid4()
    with auth_scope(user):
        cursor = encode(request, run, 123)
        assert decode(request, run, cursor) == 123
        for invalid in [
            "",
            "x" * 1025,
            cursor + "x",
            encode(request, run, -1),
            encode(request, run, True),
        ]:
            with pytest.raises(AuthError):
                decode(request, run, invalid)
        with pytest.raises(AuthError):
            decode(request, uuid4(), cursor)
    for changed in [
        Principal(uuid4(), user.tenant_id, user.roles, user.session_id),
        Principal(user.user_id, uuid4(), user.roles, user.session_id),
        Principal(user.user_id, user.tenant_id, user.roles, uuid4()),
    ]:
        with auth_scope(changed), pytest.raises(AuthError):
            decode(request, run, cursor)


def test_frames_encode_newlines_and_enforce_memory_bound():
    value = frame("change", {"text": "\nevent: forged\n<script>"}, "cursor")
    assert value.count(b"\n\n") == 1
    assert b"\nevent: forged" not in value
    assert b"id:" not in frame("reset", {})
    with pytest.raises(ValueError):
        frame("change", {"text": "x" * 16384})
    assert lock_key("tenant:a", 0) != lock_key("tenant:b", 0)
    assert lock_key("global", 0) != lock_key("global", 1)


async def test_slow_asgi_reader_disconnects_within_send_deadline():
    async def body():
        yield b"x"

    async def blocked_send(message):
        if message["type"] == "http.response.body":
            await asyncio.Event().wait()

    started = time.monotonic()
    await BoundedStream(body()).stream_response(blocked_send)
    assert 2 <= time.monotonic() - started < 5
