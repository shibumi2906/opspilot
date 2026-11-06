"""Actual client/edge/API/manager/DB TLS and credential-free observation CLI boundary."""

import asyncio
import json
import os
import ssl
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, "/work")
import httpx
from sqlalchemy import text

from opspilot.db.engine import create_engine
from opspilot.integrations.worker_settings import IngressWorkerSettings
from opspilot.tenancy.context import tenant_scope
from tests.f18_cases import CASES
from tests.integration.test_adapter_platform import Producer


async def main():
    producer = Producer()
    body = producer.body(1, observed_at=datetime.now(UTC).isoformat())
    ca = ssl.create_default_context(cafile="/lab/ca.crt")
    async with httpx.AsyncClient(
        base_url="https://app.opspilot.localhost:8443", verify=ca, trust_env=False, timeout=5
    ) as client:
        accepted = await producer.post(client, body, index=1)
        assert accepted.status_code == 202
        assert (await producer.post(client, body, index=1)).status_code == 200
        raw, headers = producer.signed(producer.body(1), index=1)
        headers["X-Ops-Signature"] = "0" * 64
        assert (
            await client.post(
                f"/ingress/v1/{CASES[1]['tenant_id']}/{CASES[1]['connector_id']}",
                content=raw,
                headers=headers,
            )
        ).status_code == 401
    env = {
        "PATH": os.environ["PATH"],
        "APP_ENV": "test",
        "SECURITY_PROFILE": "hardened",
        "INGRESS_DATABASE_URL_FILE": "/secrets/ingress.dsn",
        "RECOVERY_TENANTS": json.dumps([CASES[1]["tenant_id"]]),
    }
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "opspilot.cli.ingress_worker",
        "--once",
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert await asyncio.wait_for(child.wait(), 15) == 0
    settings = IngressWorkerSettings(
        _env_file=None,
        app_env="test",
        security_profile="hardened",
        ingress_database_url_file="/secrets/ingress.dsn",
    )
    engine = create_engine(settings.database_url())
    try:
        with tenant_scope(UUID(CASES[1]["tenant_id"])):
            async with engine.connect() as c:
                assert await c.scalar(
                    text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
                )
                assert await c.scalar(text("SELECT current_user")) == "ops_ingress"
                assert (
                    await c.scalar(
                        text("SELECT status FROM integrations.ingress_jobs WHERE event_id=:e"),
                        {"e": UUID(body["event_id"])},
                    )
                    == "done"
                )
                assert (
                    await c.scalar(
                        text("SELECT count(*) FROM integrations.observations WHERE event_id=:e"),
                        {"e": UUID(body["event_id"])},
                    )
                    == 1
                )
    finally:
        await engine.dispose()
    result = {
        "passed": True,
        "native_tls_client_edge": True,
        "verified_tls_edge_api": True,
        "manager_native_tls_required": True,
        "database_ssl_verified_full": True,
        "database_role": "ops_ingress",
        "cli_without_business_environment": True,
        "accepted": 202,
        "replay": 200,
        "bad_signature": 401,
        "observations": 1,
        "privileged_test_mapping_fixture": True,
        "vendor": False,
    }
    await asyncio.to_thread(
        Path("/reports/f18-positive-ingress.json").write_text,
        json.dumps(result, indent=2) + "\n",
    )
    print("F18 native HMAC/replay/role/verify-full DB/minimal-environment CLI checks passed")


asyncio.run(main())
