"""Readiness accepts supported Jira schemas and fails closed for unknown schemas."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from opspilot.api.routes_health import health


@pytest.mark.parametrize(
    "revision,expected",
    [
        ("0020_prometheus", 200),
        ("0021_worker_admission", 200),
        ("0022_jira_operations", 200),
        ("0023_jira_audit", 200),
        ("0019_adapters", 503),
        ("9999_unknown", 503),
        (None, 503),
    ],
)
async def test_schema_readiness(revision, expected):
    connection = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock(return_value=revision))

    @asynccontextmanager
    async def connect():
        yield connection

    @asynccontextmanager
    async def session():
        yield object(), None

    state = SimpleNamespace(
        engine=SimpleNamespace(connect=connect),
        mcp=SimpleNamespace(
            settings=SimpleNamespace(local_demo_tenant=UUID(int=1)),
            session=session,
            discover=AsyncMock(),
        ),
    )
    response = await health(SimpleNamespace(app=SimpleNamespace(state=state)))
    assert response.status_code == expected
    assert json.loads(response.body)["status"] == ("ready" if expected == 200 else "unavailable")
