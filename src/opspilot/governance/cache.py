"""Disposable, authenticated Redis accelerator; never an authorization/quota authority."""

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

from loguru import logger
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from opspilot.auth.context import actor_id
from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.tenancy.context import require_tenant

CACHEABLE = {
    "find_customers",
    "get_customer",
    "get_service_status",
    "get_integration_events",
    "search_incidents",
    "search_documentation",
}
MAX_BYTES = 65536
READ = (
    "local v=redis.call('GET',KEYS[1]); "
    "if v and string.len(v)<=65536 then return v end; return false"
)
RATE = (
    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],61) end; return n"
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


class ReadCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: Redis | None = None
        self.unavailable_until = 0.0
        self.key = (
            settings.cache_signing_key.get_secret_value().encode()
            if settings.cache_signing_key
            else b""
        )
        if settings.redis_url:
            options: dict[str, Any] = {}
            if settings.redis_url.get_secret_value().startswith("rediss:"):
                options = {
                    "ssl_ca_certs": settings.tls_ca_file,
                    "ssl_cert_reqs": "required",
                    "ssl_check_hostname": True,
                }
            self.client = Redis.from_url(
                settings.redis_url.get_secret_value(),
                username="cache",
                password=settings.redis_password.get_secret_value()
                if settings.redis_password
                else None,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                max_connections=8,
                retry=Retry(NoBackoff(), 0),
                decode_responses=False,
                **options,
            )

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def context(
        self, tool: str, arguments: dict[str, Any], source: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "protocol": 1,
            "tenant": str(require_tenant()),
            "actor": str(actor_id()),
            "customer": arguments.get("customer_id", "tenant-wide"),
            "tool": tool,
            "arguments": arguments,
            "source": source,
            "scenario": self.settings.scenario_id,
            "clock": self.settings.scenario_clock.isoformat(),
        }

    def cache_key(self, context: dict[str, Any]) -> str:
        return "opspilot-full:read:" + hashlib.sha256(canonical(context)).hexdigest()

    async def command(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if self.client is None or time.monotonic() < self.unavailable_until:
            return None
        try:
            async with asyncio.timeout(0.25):
                return await getattr(self.client, method)(*args, **kwargs)
        except (RedisError, TimeoutError, OSError):
            self.unavailable_until = time.monotonic() + 5
            logger.warning("redis_accelerator_unavailable")
            return None

    async def rate(self, source: dict[str, Any]) -> bool:
        # PostgreSQL has already charged actor/tenant/global admission on every call.
        # Losing/evicting this faster duplicate counter cannot grant extra DB capacity.
        scope = {
            "namespace": source["namespace"],
            "tenant": str(require_tenant()),
            "actor": str(actor_id()),
            "minute": int(time.time() // 60),
        }
        key = "opspilot-full:rate:" + hashlib.sha256(canonical(scope)).hexdigest()
        n = await self.command("eval", RATE, 1, key)
        return n is None or int(n) <= 600

    async def get(self, context: dict[str, Any]) -> ToolResult | None:
        if context["tool"] not in CACHEABLE or not self.key:
            return None
        raw = await self.command("eval", READ, 1, self.cache_key(context))
        if not raw:
            return None
        try:
            envelope = json.loads(raw)
            body = envelope["body"]
            expected = hmac.new(
                self.key, b"opspilot-read-v1:" + canonical(body), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, envelope["mac"]) or body["scope"] != context:
                return None
            now = time.time()
            ttl = 60 if context["tool"].startswith("search_") else 15
            if not body["created"] <= now < body["expires"] <= body["created"] + ttl:
                return None
            result = ToolResult.model_validate(body["result"])
            return result if result.ok else None
        except (ValueError, TypeError, KeyError):
            return None

    async def put(self, context: dict[str, Any], result: ToolResult) -> None:
        if context["tool"] not in CACHEABLE or not self.key or not result.ok:
            return
        ttl = 60 if context["tool"].startswith("search_") else 15
        now = time.time()
        body = {
            "scope": context,
            "created": now,
            "expires": now + ttl,
            "result": result.model_dump(mode="json"),
        }
        envelope = canonical(
            {
                "body": body,
                "mac": hmac.new(
                    self.key, b"opspilot-read-v1:" + canonical(body), hashlib.sha256
                ).hexdigest(),
            }
        )
        if len(envelope) <= MAX_BYTES:
            await self.command("set", self.cache_key(context), envelope, ex=ttl)
