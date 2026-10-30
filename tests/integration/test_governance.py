"""Real PostgreSQL/Redis resource controls; provider transport is explicitly synthetic."""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.agent.budgets import Budget, BudgetExceeded, BudgetLimits
from opspilot.agent.runtime import Runtime
from opspilot.agent.service import run_investigation
from opspilot.agent.state import Classification
from opspilot.auth.context import Principal, auth_scope
from opspilot.contracts.api import CreateRun
from opspilot.contracts.common import ToolResult
from opspilot.db.engine import create_engine
from opspilot.governance.cache import ReadCache
from opspilot.governance.usage import reserve, settle, synchronize
from opspilot.llm.base import ProviderFailure, Usage
from opspilot.llm.real import RealProvider
from opspilot.llm.scripted import ScriptedProvider
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.fencing import Fence, execution_lease, fence_scope
from opspilot.runtime.jobs import claim, finish
from opspilot.runtime.run_service import RunService


@pytest.fixture
async def governed_identity(admin_engine):
    user, tenants = uuid4(), (uuid4(), uuid4())
    async with admin_engine.begin() as c:
        await c.execute(
            text("INSERT INTO identity.users(id,issuer,subject) VALUES(:u,'urn:f15:test',:s)"),
            {"u": user, "s": str(user)},
        )
        for tenant in tenants:
            await c.execute(
                text("INSERT INTO identity.tenants(id,name) VALUES(:t,'F15 isolated fixture')"),
                {"t": tenant},
            )
            await c.execute(
                text("INSERT INTO identity.tenant_memberships VALUES(:t,:u,'operator')"),
                {"t": tenant, "u": user},
            )
    try:
        with auth_scope(Principal(user, tenants[0], frozenset({"operator"}), uuid4())):
            yield user, tenants
    finally:
        # Keep immutable resource/event evidence; only quiesce these synthetic jobs.
        async with admin_engine.begin() as c:
            for tenant in tenants:
                await c.execute(
                    text(
                        "UPDATE workflow.command_jobs SET "
                        "status='done',finished_at=clock_timestamp() WHERE tenant_id=:t"
                    ),
                    {"t": tenant},
                )
                await c.execute(
                    text(
                        "UPDATE workflow.agent_runs SET status='cancelled' WHERE tenant_id=:t "
                        "AND status IN "
                        "('queued','running','waiting_for_input','waiting_for_approval')"
                    ),
                    {"t": tenant},
                )
                await c.execute(
                    text(
                        "UPDATE workflow.run_execution_leases SET "
                        "owner=NULL,lease_until=clock_timestamp() WHERE tenant_id=:t"
                    ),
                    {"t": tenant},
                )


@asynccontextmanager
async def policy(engine, **values):
    async with engine.begin() as c:
        old = (await c.execute(text("SELECT * FROM workflow.resource_policy"))).mappings().one()
        saved = {key: old[key] for key in values}
        await c.execute(
            text("UPDATE workflow.resource_policy SET " + ",".join(f"{k}=:{k}" for k in values)),
            values,
        )
    try:
        yield
    finally:
        async with engine.begin() as c:
            await c.execute(
                text("UPDATE workflow.resource_policy SET " + ",".join(f"{k}=:{k}" for k in saved)),
                saved,
            )


@asynccontextmanager
async def owned(settings, limits=None):
    result = await run_investigation(
        settings,
        "F15 synthetic resource probe",
        queued_only=True,
        provider=ScriptedProvider(),
        limits=limits,
    )
    run = UUID(result["run_id"])
    engine = create_engine(settings.database_url("workflow"))
    try:
        async with execution_lease(engine, run, settings):
            yield run, engine
    finally:
        await engine.dispose()


async def test_attempts_unknown_cached_cost_and_restart(
    integration_settings, admin_engine, governed_identity
):
    async with owned(integration_settings) as (run, engine):
        unknown, known = uuid4(), uuid4()
        await reserve("llm", unknown, model="gpt-5-mini", tokens=8000, timeout_ms=30000)
        await settle(unknown, Usage(), "gpt-5-mini", 20)
        await reserve("llm", known, model="gpt-5-mini", tokens=8000, timeout_ms=30000)
        await settle(
            known,
            Usage(input_tokens=100, output_tokens=20, cached_input_tokens=40),
            "gpt-5-mini-2025-08-07",
            20,
        )
        restored = Budget(BudgetLimits())
        await synchronize(restored)
        assert restored.llm_attempts == 2 and restored.unknown_usage_count == 1
        assert restored.reserved_tokens == 8000
        assert restored.input_tokens == 100 and restored.output_tokens == 20
        assert restored.durable["known_spend_usd"] == pytest.approx(0.000056)
        assert restored.durable["reserved_spend_usd"] == pytest.approx(0.016)
        assert restored.durable["cost_status"] == "partial"
        with pytest.raises(RuntimeError, match="settlement rejected"):
            await settle(known, Usage(input_tokens=0, output_tokens=0), "gpt-5-mini", 0)
        with auth_scope(
            Principal(
                governed_identity[0], governed_identity[1][1], frozenset({"operator"}), uuid4()
            )
        ):
            async with engine.connect() as c:
                assert (
                    await c.scalar(text("SELECT workflow.usage_snapshot(:r)"), {"r": run}) is None
                )
        async with engine.connect() as c:
            with pytest.raises(DBAPIError):
                await c.execute(text("UPDATE workflow.provider_attempts SET held_tokens=0"))
    # Losing the original connection/lease cannot refund an uncertain provider call.
    async with admin_engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT held_tokens,status FROM workflow.provider_attempts WHERE attempt_id=:a"
                ),
                {"a": unknown},
            )
        ).one()
        assert row.held_tokens == 8000 and row.status == "unknown"


async def test_atomic_global_and_actor_token_admission(
    integration_settings, admin_engine, governed_identity
):
    async with owned(integration_settings) as (run, engine):
        async with admin_engine.connect() as c:
            count = await c.scalar(
                text(
                    "SELECT count(*) FROM workflow.provider_attempts WHERE "
                    "created_at>=clock_timestamp()-interval '1 hour' AND model<>'scripted'"
                )
            )
        async with policy(admin_engine, llm_global_hour=count + 2):

            async def attempt():
                try:
                    await reserve("llm", uuid4(), model="unpriced-fixture", tokens=4000)
                    return True
                except BudgetExceeded:
                    return False

            assert sum(await asyncio.gather(*(attempt() for _ in range(8)))) == 2
        budget = Budget(BudgetLimits())
        await synchronize(budget)
        assert budget.llm_attempts == 2 and budget.reserved_tokens == 8000
        # A stricter actor token window cannot be bypassed by another run or fresh client.
        async with policy(admin_engine, tokens_actor_hour=8000):
            with pytest.raises(BudgetExceeded):
                await reserve("llm", uuid4(), model="unpriced-fixture", tokens=1)
        await reserve("read")
        await synchronize(budget)
        assert budget.read_attempts == 1


async def test_durable_research_limits_and_unpriced_tokens(integration_settings, governed_identity):
    async with owned(integration_settings, BudgetLimits(reads=2, rounds=1)):
        await reserve("read")
        await reserve("read")
        await reserve("round")
        with pytest.raises(BudgetExceeded):
            await reserve("read")
        with pytest.raises(BudgetExceeded):
            await reserve("round")
        restored = Budget(BudgetLimits(reads=2, rounds=1))
        await synchronize(restored)
        assert restored.read_attempts == 2 and restored.rounds == 1
        await synchronize(restored, save_elapsed=True)
        assert restored.snapshot()["active_seconds"] > 0
        identity = uuid4()
        await reserve("llm", identity, model="no-reviewed-price", tokens=1000)
        await settle(
            identity,
            Usage(input_tokens=10, output_tokens=2, cached_input_tokens=0),
            "no-reviewed-price",
            1,
        )
        await synchronize(restored)
        assert restored.durable["cost_status"] == "partial"
        assert restored.input_tokens == 10 and restored.output_tokens == 2
        assert restored.reserved_tokens == 0


async def test_real_adapter_timeout_charged_without_paid_calls(
    integration_settings, governed_identity
):
    requests = []

    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout("synthetic transport timeout")

    settings = integration_settings.model_copy(
        update={
            "llm_mode": "real",
            "openai_model": "gpt-5-mini",
            "openai_api_key": SecretStr("synthetic-no-network-key"),
        }
    )
    async with owned(integration_settings) as (run, _):
        provider = RealProvider(settings, transport=httpx.MockTransport(timeout))
        runtime = Runtime(settings, provider, Budget(BudgetLimits()))
        with pytest.raises(ProviderFailure):
            await runtime.llm(
                "classify",
                {"request": "synthetic timeout fixture"},
                Classification,
                {"run_id": str(run)},
            )
        assert len(requests) == 2
        restored = Budget(BudgetLimits())
        await synchronize(restored)
        assert restored.llm_attempts == 2 and restored.unknown_usage_count == 2
        assert restored.reserved_tokens > 0 and restored.durable["cost_status"] == "partial"


async def test_redis_scope_mac_poison_expiry_and_exclusions(
    integration_settings, governed_identity, monkeypatch
):
    cache = ReadCache(integration_settings)
    source = {"namespace": str(uuid4()), "version": 1}
    context = cache.context("get_service_status", {"customer_id": str(uuid4())}, source)
    result = ToolResult(
        ok=True, observed_at=integration_settings.scenario_clock, data={"status": "degraded"}
    )
    try:
        await cache.put(context, result)
        assert (await cache.get(context)).data == result.data
        raw = await cache.command("get", cache.cache_key(context))
        with auth_scope(
            Principal(
                governed_identity[0], governed_identity[1][1], frozenset({"operator"}), uuid4()
            )
        ):
            other = cache.context("get_service_status", context["arguments"], source)
            assert cache.cache_key(context) != cache.cache_key(other)
            await cache.command("set", cache.cache_key(other), raw, ex=15)
            assert await cache.get(other) is None  # Authentic envelope cannot cross tenant scope.
        poisoned = json.loads(raw)
        poisoned["body"]["result"]["data"]["status"] = "healthy"
        await cache.command("set", cache.cache_key(context), json.dumps(poisoned), ex=15)
        assert await cache.get(context) is None
        await cache.command("set", cache.cache_key(context), b"x" * 70000, ex=15)
        assert await cache.get(context) is None
        for tool in ("get_credential_status", "get_ticket", "get_notification", "create_ticket"):
            private = cache.context(tool, {}, source)
            await cache.put(private, result)
            assert await cache.command("get", cache.cache_key(private)) is None
        await cache.put(context, result)
        now = time.time()
        monkeypatch.setattr("opspilot.governance.cache.time.time", lambda: now + 16)
        assert await cache.get(context) is None
    finally:
        await cache.close()


async def test_live_mcp_cache_invalidation_and_revoked_actor(
    integration_settings, admin_engine, governed_identity
):
    customer = uuid4()
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO domain.customers(id,tenant_id,name,normalized_name,metadata) "
                "VALUES(:id,:t,'F15 before','f15 before','{}')"
            ),
            {"id": customer, "t": governed_identity[1][0]},
        )
    client = MCPClient(integration_settings)
    async with client.session() as (session, _):
        first = await client.call(session, "get_customer", {"customer_id": str(customer)})
        second = await client.call(session, "get_customer", {"customer_id": str(customer)})
        assert first.ok and second.data == first.data and first.data["name"] == "F15 before"
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE domain.customers SET name='F15 after' WHERE id=:id"), {"id": customer}
            )
        third = await client.call(session, "get_customer", {"customer_id": str(customer)})
        assert third.ok and third.data["name"] == "F15 after"
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE identity.users SET disabled_at=clock_timestamp() WHERE id=:u"),
                {"u": governed_identity[0]},
            )
        denied = await client.call(session, "get_customer", {"customer_id": str(customer)})
        assert not denied.ok and denied.error.code == "ACCESS_DENIED"


async def test_durable_source_rate_not_refunded_by_redis_loss(
    integration_settings, admin_engine, governed_identity
):
    engine = create_engine(integration_settings.database_url("domain"))
    down = ReadCache(
        integration_settings.model_copy(update={"redis_url": SecretStr("redis://127.0.0.1:1/0")})
    )
    try:
        async with policy(admin_engine, source_actor_minute=1):
            async with engine.begin() as c:
                assert await c.scalar(text("SELECT workflow.consume_source_budget()"))
            started = time.monotonic()
            assert (
                await down.get(
                    down.context(
                        "get_service_status", {}, {"namespace": str(uuid4()), "version": 1}
                    )
                )
                is None
            )
            assert time.monotonic() - started < 1
            async with engine.begin() as c:
                assert not await c.scalar(text("SELECT workflow.consume_source_budget()"))
            # A new Redis client (empty/new accelerator state) still cannot reset PG admission.
            fresh = ReadCache(integration_settings)
            await fresh.close()
            async with engine.begin() as c:
                assert not await c.scalar(text("SELECT workflow.consume_source_budget()"))
    finally:
        await down.close()
        await engine.dispose()


async def test_fair_worker_admission_uses_live_durable_leases(
    integration_settings, admin_engine, governed_identity
):
    user, tenants = governed_identity
    jobs = []
    engines = []
    try:
        for tenant in tenants:
            with auth_scope(Principal(user, tenant, frozenset({"operator"}), uuid4())):
                service = RunService(integration_settings)
                engines.append(service)
                for _ in range(2):
                    await service.create(
                        CreateRun(request="F15 fairness", client_request_id=uuid4())
                    )
        async with admin_engine.begin() as c:
            for index, tenant in enumerate(tenants):
                await c.execute(
                    text(
                        "UPDATE workflow.command_jobs SET created_at=CAST(:stamp AS timestamptz) "
                        "WHERE tenant_id=:t"
                    ),
                    {"t": tenant, "stamp": f"1900-01-0{index + 1}T00:00:00Z"},
                )
        async with policy(admin_engine, worker_global=4, worker_tenant=2, worker_actor=2):
            with auth_scope(Principal(user, tenants[0], frozenset({"operator"}), uuid4())):
                a = await claim(engines[0].engine, eligible_tenants=tenants)
                assert a is not None
                jobs.append((0, a))
                assert (
                    await claim(engines[0].engine, eligible_tenants=tenants) is None
                )  # Other tenant's turn, free slots remain.
            with auth_scope(Principal(user, tenants[1], frozenset({"operator"}), uuid4())):
                b = await claim(engines[1].engine, eligible_tenants=tenants)
                assert b is not None
                jobs.append((1, b))
                assert (
                    await claim(engines[1].engine, eligible_tenants=tenants) is None
                )  # Shared actor cap, not an in-process lock.
    finally:
        for index, job in jobs:
            with auth_scope(Principal(user, tenants[index], frozenset({"operator"}), uuid4())):
                async with execution_lease(
                    engines[index].engine,
                    job["run_id"],
                    integration_settings,
                    Fence(job["run_id"], job["claim_owner"], job["claim_epoch"]),
                ):
                    await finish(engines[index].engine, job)
        for service in engines:
            await service.close()


@pytest.mark.skipif(
    os.environ.get("TEST_F15_REDIS_DOWN") != "1", reason="Dedicated real Redis stop/restart gate"
)
async def test_real_redis_outage_bounded_direct_read(integration_settings):
    client = MCPClient(integration_settings)
    async with client.session() as (session, _):
        result = await client.call(session, "find_customers", {"query": "GreenShop", "limit": 2})
        assert result.ok and result.data["candidates"]


async def test_tenant_global_token_and_known_spend_caps(
    integration_settings, admin_engine, governed_identity
):
    async with owned(integration_settings):
        first = uuid4()
        await reserve("llm", first, model="gpt-5-mini", tokens=8000)
        async with policy(admin_engine, tokens_tenant_hour=8000):
            with pytest.raises(BudgetExceeded):
                await reserve("llm", uuid4(), model="gpt-5-mini", tokens=1)
        async with admin_engine.connect() as c:
            used = await c.scalar(
                text(
                    "SELECT "
                    "COALESCE(sum(COALESCE(input_tokens,0)+"
                    "COALESCE(output_tokens,0)+held_tokens),0) "
                    "FROM workflow.provider_attempts WHERE "
                    "created_at>=clock_timestamp()-interval '1 hour' "
                    "AND model<>'scripted'"
                )
            )
        async with policy(admin_engine, tokens_global_hour=int(used) + 1):
            await reserve("llm", uuid4(), model="unpriced-fixture", tokens=1)
            with pytest.raises(BudgetExceeded):
                await reserve("llm", uuid4(), model="unpriced-fixture", tokens=1)
        model = "f15-expensive-" + str(uuid4())
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO workflow.model_prices VALUES(:m,'synthetic-price-cap','USD',"
                    "clock_timestamp()-interval '1 "
                    "day',clock_timestamp(),clock_timestamp()+interval '1 day',"
                    "'urn:opspilot:synthetic-price-test',1000,1000,1000)"
                ),
                {"m": model},
            )
        with pytest.raises(BudgetExceeded):
            await reserve("llm", uuid4(), model=model, tokens=1000)
        # Existing held spend remains authoritative even when all accelerator state is lost.
        async with policy(admin_engine, spend_actor_hour=0.016):
            with pytest.raises(BudgetExceeded):
                await reserve("llm", uuid4(), model="gpt-5-mini", tokens=1)


@pytest.mark.skipif(
    os.environ.get("TEST_F15_PROCESS") != "1", reason="Dedicated crash/restart gate"
)
async def test_crash_after_dispatch_reservation_keeps_unknown_budget(
    integration_settings, admin_engine, governed_identity
):
    import subprocess
    import sys

    user, tenants = governed_identity
    queued = await run_investigation(
        integration_settings,
        "F15 crash accounting fixture",
        queued_only=True,
        provider=ScriptedProvider(),
    )
    run = UUID(queued["run_id"])
    script = r"""
import asyncio,os
from uuid import UUID,uuid4
import httpx
from pydantic import SecretStr
from opspilot.agent.budgets import Budget,BudgetLimits
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import Classification
from opspilot.auth.context import Principal,auth_scope
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.llm.real import RealProvider
from opspilot.runtime.fencing import execution_lease
async def main():
 s=Settings().model_copy(update={'llm_mode':'real','openai_model':'gpt-5-mini',
   'openai_api_key':SecretStr('synthetic-no-network-key'),
   'worker_lease_seconds':1,'worker_heartbeat_seconds':.2})
 engine=create_engine(s.database_url('workflow'))
 def crash(request):os._exit(77)
 with auth_scope(Principal(UUID(os.environ['F15_ACTOR']),UUID(os.environ['F15_TENANT']),
                           frozenset({'operator'}),uuid4())):
  async with execution_lease(engine,UUID(os.environ['F15_RUN']),s):
   provider=RealProvider(s,transport=httpx.MockTransport(crash))
   await Runtime(s,provider,Budget(BudgetLimits())).llm('classify',{'request':'synthetic crash'},
     Classification,{'run_id':os.environ['F15_RUN']})
asyncio.run(main())
"""
    env = {**os.environ, "F15_ACTOR": str(user), "F15_TENANT": str(tenants[0]), "F15_RUN": str(run)}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 77, (stdout.decode(), stderr.decode())
    async with admin_engine.connect() as c:
        original = (
            (
                await c.execute(
                    text("SELECT * FROM workflow.provider_attempts WHERE run_id=:r"), {"r": run}
                )
            )
            .mappings()
            .one()
        )
        assert original["status"] == "started" and original["held_tokens"] > 0
        stale = (
            await c.execute(
                text("SELECT owner,epoch FROM workflow.run_execution_leases WHERE run_id=:r"),
                {"r": run},
            )
        ).one()
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        await asyncio.sleep(1.2)
        async with execution_lease(engine, run, integration_settings):
            restored = Budget(BudgetLimits())
            await synchronize(restored)
            assert restored.llm_attempts == 1 and restored.unknown_usage_count == 1
            assert restored.reserved_tokens == original["held_tokens"]
            assert restored.snapshot()["active_seconds"] >= 30
            with fence_scope(Fence(run, stale.owner, stale.epoch)):
                with pytest.raises(DBAPIError) as rejected:
                    await settle(
                        original["attempt_id"],
                        Usage(input_tokens=0, output_tokens=0),
                        "gpt-5-mini",
                        0,
                    )
                assert rejected.value.orig.sqlstate == "40001"
            second = uuid4()
            await reserve("llm", second, model="gpt-5-mini", tokens=1000)
            await settle(
                second,
                Usage(input_tokens=10, output_tokens=1, cached_input_tokens=0),
                "gpt-5-mini",
                1,
            )
            await synchronize(restored)
            assert restored.llm_attempts == 2 and restored.unknown_usage_count == 1
            assert restored.reserved_tokens == original["held_tokens"]
    finally:
        await engine.dispose()


async def test_actor_admission_spans_tenants_and_invalid_limits_fail_closed(
    integration_settings, admin_engine, governed_identity
):
    settings = integration_settings.model_copy(update={"max_actor_active_runs": 1})
    service = RunService(settings)
    user, tenants = governed_identity
    try:
        first = await service.create(
            CreateRun(request="F15 active capacity", client_request_id=uuid4())
        )
        with auth_scope(Principal(user, tenants[1], frozenset({"operator"}), uuid4())):
            with pytest.raises(DBAPIError) as limited:
                await service.create(
                    CreateRun(request="F15 cross-tenant capacity", client_request_id=uuid4())
                )
            assert limited.value.orig.sqlstate == "P0001"
        with pytest.raises(DBAPIError):
            async with admin_engine.begin() as c:
                await c.execute(
                    text("UPDATE workflow.usage_reservations SET limits='{}' WHERE run_id=:r"),
                    {"r": UUID(first["run_id"])},
                )
    finally:
        await service.close()


async def test_unexpected_provider_tier_remains_unpriced(
    integration_settings, admin_engine, governed_identity
):
    seen = []

    def transport(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gpt-5-mini",
                "service_tier": "priority",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 40},
                },
                "output": [],
            },
        )

    settings = integration_settings.model_copy(
        update={
            "openai_model": "gpt-5-mini",
            "openai_api_key": SecretStr("synthetic-no-network-key"),
        }
    )
    provider = RealProvider(settings, transport=httpx.MockTransport(transport))
    completion = await provider.complete("investigate", {})
    assert seen[0]["service_tier"] == "default"
    assert not completion.usage.standard_pricing
    async with owned(integration_settings) as (run, _):
        identity = uuid4()
        await reserve("llm", identity, model="gpt-5-mini", tokens=1000)
        await settle(identity, completion.usage, completion.model_id, 1)
        restored = Budget(BudgetLimits())
        await synchronize(restored)
        assert restored.durable["cost_status"] == "partial"
        assert restored.durable["known_spend_usd"] == 0
        async with admin_engine.connect() as c:
            row = (
                await c.execute(
                    text(
                        "SELECT cached_tokens,standard_pricing,known_cost,held_cost "
                        "FROM workflow.provider_attempts WHERE run_id=:r"
                    ),
                    {"r": run},
                )
            ).one()
            assert row.cached_tokens == 40 and row.standard_pricing is False
            assert row.known_cost is None and row.held_cost > 0


async def test_source_versions_do_not_serialize_unrelated_mutations(
    integration_settings, admin_engine, governed_identity
):
    user, tenants = governed_identity
    first, second = uuid4(), uuid4()
    domain = create_engine(integration_settings.database_url("domain"))

    async def version():
        async with domain.begin() as c:
            return await c.scalar(text("SELECT workflow.cache_source_version()"))

    try:
        before = await version()
        async with admin_engine.connect() as a, admin_engine.connect() as b:
            ta, tb = await a.begin(), await b.begin()
            try:
                query = text(
                    "INSERT INTO domain.customers(id,tenant_id,name,normalized_name,metadata) "
                    "VALUES(:id,:tenant,'F15 source','f15 source','{}')"
                )
                await a.execute(query, {"id": first, "tenant": tenants[0]})
                async with asyncio.timeout(5):
                    await b.execute(query, {"id": second, "tenant": tenants[0]})
                    await tb.commit()
                # Commit order differs from allocation/write order, but no version is missed.
                middle = await version()
                assert middle["version"] == before["version"] + 1
                await ta.commit()
                after = await version()
                assert after["version"] == middle["version"] + 1
                assert after["namespace"] == before["namespace"]
            finally:
                if ta.is_active:
                    await ta.rollback()
                if tb.is_active:
                    await tb.rollback()
        client = MCPClient(integration_settings)
        async with client.session() as (session, _):
            assert (await client.call(session, "get_customer", {"customer_id": str(first)})).ok
            async with admin_engine.begin() as c:
                await c.execute(
                    text("UPDATE domain.customers SET tenant_id=:tenant WHERE id=:id"),
                    {"tenant": tenants[1], "id": first},
                )
            denied = await client.call(session, "get_customer", {"customer_id": str(first)})
            assert not denied.ok and denied.error.code == "NOT_FOUND"
        with auth_scope(Principal(user, tenants[1], frozenset({"operator"}), uuid4())):
            async with client.session() as (session, _):
                assert (await client.call(session, "get_customer", {"customer_id": str(first)})).ok
    finally:
        await domain.dispose()
