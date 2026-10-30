"""Native Redis TLS/authentication/cache proof in the isolated synthetic lab."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr
from redis.exceptions import RedisError

from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.governance.cache import ReadCache
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope


async def main():
    env = Settings(_env_file=None)
    settings = env.model_copy(
        update={
            "redis_url": SecretStr("rediss://redis:6379/0"),
            "redis_password": SecretStr(
                (await asyncio.to_thread(Path("/lab/redis.password").read_text)).strip()
            ),
            "cache_signing_key": SecretStr(
                (await asyncio.to_thread(Path("/lab/cache-signing.key").read_text)).strip()
            ),
        }
    )
    checks = []
    good = ReadCache(settings)
    try:
        assert await good.client.ping()
        checks.append("Native TLS with trusted CA and Redis cache ACL password succeeds")
        with tenant_scope(DEMO_TENANT):
            context = good.context(
                "get_service_status", {}, {"namespace": str(uuid4()), "version": 1}
            )
            value = ToolResult(
                ok=True, observed_at=settings.scenario_clock, data={"status": "degraded"}
            )
            await good.put(context, value)
            assert (await good.get(context)).data == value.data
        checks.append("Authenticated scoped HMAC cache read/write over TLS succeeds")
    finally:
        await good.close()
    for name, patch in [
        ("Untrusted Redis CA rejected", {"tls_ca_file": None}),
        (
            "Wrong Redis TLS hostname rejected",
            {"redis_url": SecretStr("rediss://redis-wrong:6379/0")},
        ),
        ("Invalid Redis ACL password rejected", {"redis_password": SecretStr("x" * 64)}),
    ]:
        wrong = ReadCache(settings.model_copy(update=patch))
        try:
            try:
                await wrong.client.ping()
            except (RedisError, OSError):
                checks.append(name)
            else:
                raise AssertionError(name)
        finally:
            await wrong.close()
    reader, writer = await asyncio.open_connection("redis", 6379)
    writer.write(b"*1\r\n$4\r\nPING\r\n")
    try:
        try:
            plain = await asyncio.wait_for(reader.read(64), 0.5)
        except (TimeoutError, ConnectionError):
            plain = b""
        assert b"+PONG" not in plain
        checks.append("Plaintext Redis protocol cannot use the native TLS listener")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass
    report = {
        "passed": True,
        "checks": checks,
        "synthetic": True,
        "plaintext_redis_listener": False,
    }
    await asyncio.to_thread(
        Path("/reports/redis-tls.json").write_text, json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))


asyncio.run(main())
