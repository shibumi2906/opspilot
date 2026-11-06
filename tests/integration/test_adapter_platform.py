"""Real HTTP(S), OpenBao, PostgreSQL and process boundaries. No vendor/staging claims."""

import asyncio
import hashlib
import hmac
import json
import os
import socket
import ssl
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.api.routes_ingress import signature_input
from opspilot.db.engine import create_engine
from opspilot.integrations.contracts import AdapterScope
from opspilot.integrations.egress import ConnectorUnavailable, health
from opspilot.integrations.service import process_one
from opspilot.mcp_client.client import MCPClient
from opspilot.tenancy.context import tenant_scope
from tests.auth_helpers import session_client
from tests.f18_cases import CASES

pytestmark = pytest.mark.skipif(
    os.environ.get("F18_CONTRACT") != "1", reason="Dedicated real F18 transport profile"
)


class Producer:
    def __init__(self):
        self.private = json.loads(Path("/run/f18-probe/fixture.json").read_text())

    def __repr__(self):
        return "<F18 producer credentials redacted>"

    def body(self, index=0, **overrides):
        case = CASES[index]
        return {
            "event_id": str(uuid4()),
            "sequence": time.time_ns() // 1000,
            "customer_id": case["customer_id"],
            "integration_id": case["integration_id"],
            "status": "healthy",
            "observed_at": datetime.now(UTC).isoformat(),
            **overrides,
        }

    def signed(self, body, index=0, kid="h2", timestamp=None, raw=None):
        case = CASES[index]
        payload = raw if raw is not None else json.dumps(body, separators=(",", ":")).encode()
        stamp = timestamp or str(int(time.time()))
        digest = hmac.new(
            bytes.fromhex(self.private["cases"][index]["keys"][kid]),
            signature_input(UUID(case["tenant_id"]), UUID(case["connector_id"]), stamp, payload),
            hashlib.sha256,
        ).hexdigest()
        return payload, {
            "Content-Type": "application/json",
            "X-Ops-Timestamp": stamp,
            "X-Ops-Key-Id": kid,
            "X-Ops-Signature": digest,
        }

    async def post(self, client, body=None, index=0, kid="h2", **options):
        body = body or self.body(index)
        raw, headers = self.signed(body, index, kid, **options)
        case = CASES[index]
        return await client.post(
            f"/ingress/v1/{case['tenant_id']}/{case['connector_id']}", content=raw, headers=headers
        )

    async def mode(self, connector, mode):
        context = ssl.create_default_context(cafile="/run/connectors/simulator-ca.crt")
        async with httpx.AsyncClient(verify=context, trust_env=False) as c:
            r = await c.post(
                "https://adapter-simulator:8443/__control",
                headers={"Authorization": "Bearer " + self.private["control_token"]},
                json={"connector_id": str(connector), "mode": mode},
            )
            assert r.status_code == 200
            return r.json()["hits"].get(str(connector), 0)


@pytest.fixture
def producer():
    return Producer()


@pytest.fixture
async def configured_cases(integration_settings, admin_engine, producer):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        for case in CASES:
            await session_client(c, integration_settings, "admin", UUID(case["tenant_id"]))
            current = (await c.get("/api/v2/admin/adapters")).json()["items"]
            version = next((r["version"] for r in current if r["id"] == case["connector_id"]), 0)
            r = await c.put(
                "/api/v2/admin/adapters/" + case["connector_id"],
                json={
                    "expected_version": version,
                    "customer_id": case["customer_id"],
                    "integration_id": case["integration_id"],
                    "origin": "https://adapter-simulator:8443",
                    "read_enabled": True,
                    "ingress_enabled": True,
                },
            )
            assert r.status_code == 200, r.text
            await producer.mode(case["connector_id"], "normal")
        async with admin_engine.begin() as connection:
            await connection.execute(
                text("UPDATE integrations.connector_health SET failures=0,open_until=NULL")
            )
    return CASES


async def receipt_count(engine, event):
    async with engine.connect() as c:
        return await c.scalar(
            text("SELECT count(*) FROM integrations.webhook_receipts WHERE event_id=:e"),
            {"e": UUID(event)},
        )


async def rpc(settings, case, name="get_service_status", **extra):
    with tenant_scope(UUID(case["tenant_id"])):
        async with MCPClient(settings).session() as (session, _):
            return await MCPClient.call(
                session,
                name,
                {
                    "customer_id": case["customer_id"],
                    "integration_id": case["integration_id"],
                    **extra,
                },
            )


@pytest.fixture
async def tls_api(tmp_path, integration_settings):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = (tmp_path / "api.log").open("wb")
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests.f18_server", str(port), stdout=log, stderr=log
    )
    context = ssl.create_default_context(cafile="/run/f18-probe/simulator-ca.crt")
    try:
        async with httpx.AsyncClient(
            base_url=f"https://localhost:{port}", verify=context, trust_env=False
        ) as c:
            async with asyncio.timeout(20):
                while True:
                    try:
                        if (await c.get("/health/live")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.05)
            yield c
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), 10)
        log.close()


async def test_native_https_receipt_commit_replay_and_conflict(
    tls_api, configured_cases, producer, admin_engine
):
    body = producer.body()
    assert (await producer.post(tls_api, body)).status_code == 202
    assert await receipt_count(admin_engine, body["event_id"]) == 1
    duplicate = await producer.post(tls_api, body)
    assert duplicate.status_code == 200 and duplicate.json()["replayed"]
    assert (await producer.post(tls_api, {**body, "status": "unknown"})).status_code == 409
    async with admin_engine.connect() as c:
        assert (
            await c.scalar(
                text("SELECT count(*) FROM integrations.ingress_jobs WHERE event_id=:e"),
                {"e": UUID(body["event_id"])},
            )
            == 1
        )


@pytest.mark.parametrize(
    "attack",
    [
        "signature",
        "raw_body",
        "stale",
        "future",
        "unknown_kid",
        "foreign_path",
        "foreign_mapping",
        "approval_payload",
        "duplicate_header",
        "compressed",
    ],
)
async def test_invalid_ingress_has_no_receipt_or_domain_write(
    attack, configured_cases, producer, admin_engine
):
    body = producer.body()
    raw, headers = producer.signed(body)
    path = f"/ingress/v1/{CASES[0]['tenant_id']}/{CASES[0]['connector_id']}"
    expected = {401, 400, 403}
    if attack == "signature":
        headers["X-Ops-Signature"] = "0" * 64
    if attack == "raw_body":
        raw += b" "
    if attack in {"stale", "future"}:
        raw, headers = producer.signed(
            body, timestamp=str(int(time.time()) + (-301 if attack == "stale" else 301))
        )
    if attack == "unknown_kid":
        headers["X-Ops-Key-Id"] = "absent"
    if attack == "foreign_path":
        path = f"/ingress/v1/{CASES[1]['tenant_id']}/{CASES[0]['connector_id']}"
    if attack == "foreign_mapping":
        raw, headers = producer.signed({**body, "customer_id": CASES[1]["customer_id"]})
    if attack == "approval_payload":
        raw, headers = producer.signed({**body, "status": "approved", "credential": "F18_SENTINEL"})
    if attack == "duplicate_header":
        headers = list(headers.items()) + [("X-Ops-Timestamp", str(int(time.time())))]
    if attack == "compressed":
        headers["Content-Encoding"] = "gzip"
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        r = await c.post(path, content=raw, headers=headers)
        assert r.status_code in expected and "F18_SENTINEL" not in r.text
    assert await receipt_count(admin_engine, body["event_id"]) == 0


async def test_oversized_body_denied_before_receipt(configured_cases, producer, admin_engine):
    body = producer.body()
    raw, headers = producer.signed(body, raw=b"x" * 16385)
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        r = await c.post(
            f"/ingress/v1/{CASES[0]['tenant_id']}/{CASES[0]['connector_id']}",
            content=raw,
            headers=headers,
        )
        assert r.status_code == 413
    assert await receipt_count(admin_engine, body["event_id"]) == 0


async def test_out_of_order_observation_cannot_reopen_or_write(
    configured_cases, producer, integration_settings, admin_engine
):
    sequence = time.time_ns() // 1000
    bodies = [
        producer.body(sequence=sequence),
        producer.body(sequence=sequence - 1, status="unavailable"),
    ]
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        for body in bodies:
            assert (await producer.post(c, body)).status_code == 202
    engine = create_engine(integration_settings.database_url("ingress"))
    try:
        with tenant_scope(UUID(CASES[0]["tenant_id"])):
            while await process_one(engine):
                pass
        async with admin_engine.connect() as c:
            rows = (
                (
                    await c.execute(
                        text(
                            "SELECT status FROM integrations.webhook_receipts "
                            "WHERE event_id=ANY(:ids) ORDER BY status"
                        ),
                        {"ids": [UUID(b["event_id"]) for b in bodies]},
                    )
                )
                .scalars()
                .all()
            )
            assert rows == ["ignored", "processed"]
            assert not await c.scalar(
                text("SELECT has_table_privilege('ops_ingress','domain.tickets','INSERT')")
            )
            assert not await c.scalar(
                text("SELECT has_table_privilege('ops_ingress','workflow.approvals','UPDATE')")
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "mode", ["redirect", "oversize", "slow", "wrong_scope", "invalid", "denied"]
)
async def test_http_adapter_failures_are_bounded_and_not_cached(
    mode, configured_cases, producer, integration_settings
):
    good = await rpc(integration_settings, CASES[0])
    assert good.ok and good.data["status"] == "healthy"
    await producer.mode(CASES[0]["connector_id"], mode)
    start = time.monotonic()
    result = await rpc(integration_settings, CASES[0])
    assert not result.ok and result.error.code == "DEPENDENCY_UNAVAILABLE"
    assert time.monotonic() - start < 5
    credential = await rpc(integration_settings, CASES[0], "get_credential_status")
    assert credential.ok and credential.data["status"] == "unknown"


async def test_two_tenant_http_scope_and_circuit_recovery(
    configured_cases, producer, integration_settings, admin_engine
):
    for case in CASES:
        r = await rpc(integration_settings, case)
        assert (
            r.ok
            and r.data["status"] == "healthy"
            and r.sources[0].version == "simulator-v1:synthetic"
        )
    await producer.mode(CASES[0]["connector_id"], "denied")
    for _ in range(3):
        assert not (await rpc(integration_settings, CASES[0])).ok
    before = await producer.mode(CASES[0]["connector_id"], "normal")
    assert not (await rpc(integration_settings, CASES[0])).ok
    assert await producer.mode(CASES[0]["connector_id"], "normal") == before
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "UPDATE integrations.connector_health "
                "SET open_until=clock_timestamp()-interval '1 second'"
            )
        )
    assert (await rpc(integration_settings, CASES[0])).ok


@pytest.mark.parametrize("attack", ["dns_rebind", "ca", "hostname"])
async def test_real_egress_rejects_rebinding_and_tls_peer_failure(
    attack, configured_cases, producer, integration_settings, monkeypatch
):
    case = CASES[0]
    scope = AdapterScope(**case)
    settings = integration_settings
    if attack == "ca":
        settings = settings.model_copy(
            update={"connector_simulator_ca_file": "/run/connectors/manager-ca.crt"}
        )
    if attack == "hostname":
        settings = settings.model_copy(
            update={"connector_simulator_origin": f"https://{settings.connector_simulator_ip}:8443"}
        )
    if attack == "dns_rebind":
        original = socket.getaddrinfo

        def rebound(host, *args, **kwargs):
            result = original(host, *args, **kwargs)
            return (
                result + [(*result[0][:4], ("169.254.169.254", 8443))]
                if host == "adapter-simulator"
                else result
            )

        monkeypatch.setattr(socket, "getaddrinfo", rebound)
    with pytest.raises(ConnectorUnavailable):
        await health(
            settings,
            settings.connector_simulator_origin,
            producer.private["cases"][0]["credential"],
            scope,
        )


async def test_admin_refs_scope_immutability_and_cas(
    configured_cases, producer, integration_settings
):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as c:
        await session_client(c, integration_settings, "operator")
        assert (await c.get("/api/v2/admin/adapters")).status_code == 403
        await session_client(c, integration_settings, "admin")
        response = await c.get("/api/v2/admin/adapters")
        assert response.status_code == 200
        public = response.json()
        assert "token" not in json.dumps(public) and "credential_ref" not in json.dumps(public)
        case = CASES[0]
        version = next(x["version"] for x in public["items"] if x["id"] == case["connector_id"])
        value = {
            "expected_version": version,
            "customer_id": case["customer_id"],
            "integration_id": case["integration_id"],
            "origin": "https://adapter-simulator:8443",
            "read_enabled": False,
            "ingress_enabled": False,
        }
        assert (
            await c.put("/api/v2/admin/adapters/" + case["connector_id"], json=value)
        ).status_code == 200
        assert (
            await c.put("/api/v2/admin/adapters/" + case["connector_id"], json=value)
        ).status_code == 409
        for bad in (
            {"origin": "https://169.254.169.254"},
            {"credential_ref": "connectors/foreign/credential"},
            {"write_enabled": True},
            {"mapping_version": 2},
        ):
            assert (
                await c.put("/api/v2/admin/adapters/" + case["connector_id"], json={**value, **bad})
            ).status_code == 422


async def wait_marker(marker, process):
    async with asyncio.timeout(10):
        while not marker.exists():
            assert process.returncode is None, "Fault-injection child exited early"
            await asyncio.sleep(0.02)


@pytest.mark.parametrize("phase", ["before-commit", "after-commit"])
async def test_kill_ingress_before_and_after_durable_receipt(
    phase, configured_cases, producer, admin_engine, tmp_path
):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    marker = tmp_path / "boundary"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.f18_server",
        str(port),
        str(marker),
        phase,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    body = producer.body()
    context = ssl.create_default_context(cafile="/run/f18-probe/simulator-ca.crt")
    request = None
    try:
        async with httpx.AsyncClient(
            base_url=f"https://localhost:{port}", verify=context, trust_env=False, timeout=15
        ) as client:
            async with asyncio.timeout(15):
                while True:
                    try:
                        if (await client.get("/health/live")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.05)
            request = asyncio.create_task(producer.post(client, body))
            await wait_marker(marker, child)
            assert await receipt_count(admin_engine, body["event_id"]) == (
                0 if phase == "before-commit" else 1
            )
            child.kill()
            await asyncio.wait_for(child.wait(), 5)
            with pytest.raises(httpx.HTTPError):
                await request
        async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
            r = await producer.post(client, body)
            assert r.status_code == (202 if phase == "before-commit" else 200)
            assert (await producer.post(client, body)).status_code == 200
        assert await receipt_count(admin_engine, body["event_id"]) == 1
        async with admin_engine.connect() as c:
            assert (
                await c.scalar(
                    text("SELECT count(*) FROM integrations.ingress_jobs WHERE event_id=:e"),
                    {"e": UUID(body["event_id"])},
                )
                == 1
            )
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
        if request and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)


async def test_processor_kill_rolls_back_and_two_workers_claim_once(
    configured_cases, producer, admin_engine, integration_settings, tmp_path
):
    engine = create_engine(integration_settings.database_url("ingress"))
    with tenant_scope(UUID(CASES[0]["tenant_id"])):
        while await process_one(engine):
            pass
    await engine.dispose()
    body = producer.body()
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await producer.post(client, body)).status_code == 202
    marker = tmp_path / "processing"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.f18_worker",
        str(marker),
        body["event_id"],
        CASES[0]["tenant_id"],
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await wait_marker(marker, child)
        async with admin_engine.connect() as c:
            assert (
                await c.scalar(
                    text("SELECT count(*) FROM integrations.observations WHERE event_id=:e"),
                    {"e": UUID(body["event_id"])},
                )
                == 0
            )
        child.kill()
        await asyncio.wait_for(child.wait(), 5)
        workers = [
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "opspilot.cli.ingress_worker",
                "--once",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            for _ in range(2)
        ]
        assert await asyncio.gather(*(asyncio.wait_for(w.wait(), 10) for w in workers)) == [0, 0]
        async with admin_engine.connect() as c:
            for table in ("observations", "audit"):
                condition = " AND kind='processed'" if table == "audit" else ""
                assert (
                    await c.scalar(
                        text(
                            f"SELECT count(*) FROM integrations.{table} WHERE event_id=:e"
                            + condition
                        ),
                        {"e": UUID(body["event_id"])},
                    )
                    == 1
                )
            assert (
                await c.scalar(
                    text("SELECT status FROM integrations.ingress_jobs WHERE event_id=:e"),
                    {"e": UUID(body["event_id"])},
                )
                == "done"
            )
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()


async def test_disabled_connector_quarantines_accepted_observations(
    configured_cases, producer, admin_engine, integration_settings
):
    body = producer.body()
    case = CASES[0]
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await producer.post(client, body)).status_code == 202
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE integrations.connector_configs SET ingress_enabled=false WHERE id=:c"),
                {"c": UUID(case["connector_id"])},
            )
        try:
            assert (await producer.post(client, producer.body())).status_code == 401
            engine = create_engine(integration_settings.database_url("ingress"))
            try:
                with tenant_scope(UUID(case["tenant_id"])):
                    while await process_one(engine):
                        pass
            finally:
                await engine.dispose()
            async with admin_engine.connect() as c:
                assert (
                    await c.scalar(
                        text("SELECT status FROM integrations.webhook_receipts WHERE event_id=:e"),
                        {"e": UUID(body["event_id"])},
                    )
                    == "quarantined"
                )
                assert (
                    await c.scalar(
                        text("SELECT count(*) FROM integrations.observations WHERE event_id=:e"),
                        {"e": UUID(body["event_id"])},
                    )
                    == 0
                )
        finally:
            async with admin_engine.begin() as c:
                await c.execute(
                    text(
                        "UPDATE integrations.connector_configs SET ingress_enabled=true WHERE id=:c"
                    ),
                    {"c": UUID(case["connector_id"])},
                )


async def test_ingress_budget_is_durable_and_replay_does_not_consume_it(
    configured_cases, producer, admin_engine
):
    body = producer.body()
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await producer.post(client, body)).status_code == 202
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE integrations.ingress_budgets SET used=60, "
                    "minute=floor(extract(epoch FROM clock_timestamp())/60)::bigint "
                    "WHERE connector_id=:c"
                ),
                {"c": UUID(CASES[0]["connector_id"])},
            )
        try:
            denied = producer.body()
            assert (await producer.post(client, denied)).status_code == 429
            assert (await producer.post(client, body)).status_code == 200
            assert await receipt_count(admin_engine, denied["event_id"]) == 0
        finally:
            async with admin_engine.begin() as c:
                await c.execute(
                    text("UPDATE integrations.ingress_budgets SET used=0 WHERE connector_id=:c"),
                    {"c": UUID(CASES[0]["connector_id"])},
                )


async def test_ingress_role_cannot_modify_config_or_receipt_identity_or_cross_tenant(
    configured_cases, producer, admin_engine, integration_settings
):
    from sqlalchemy.exc import DBAPIError

    body = producer.body()
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await producer.post(client, body)).status_code == 202
    engine = create_engine(integration_settings.database_url("ingress"))
    try:
        with tenant_scope(UUID(CASES[0]["tenant_id"])):
            async with engine.connect() as c:
                assert (
                    await c.scalar(
                        text("SELECT count(*) FROM integrations.lock_config(:c)"),
                        {"c": UUID(CASES[1]["connector_id"])},
                    )
                    == 0
                )
            for statement in (
                "UPDATE integrations.connector_configs SET read_enabled=false",
                "UPDATE integrations.webhook_receipts SET body_hash=repeat('0',64) "
                "WHERE event_id=:e",
                "INSERT INTO domain.tickets DEFAULT VALUES",
            ):
                with pytest.raises(DBAPIError):
                    async with engine.begin() as c:
                        await c.execute(text(statement), {"e": UUID(body["event_id"])})
        with tenant_scope(UUID(CASES[1]["tenant_id"])):
            async with engine.connect() as c:
                assert await receipt_count(engine, body["event_id"]) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("limit", ["connector", "global"])
async def test_pending_bounds_are_enforced_across_tenants(
    limit, configured_cases, producer, admin_engine
):
    filler = CASES[0 if limit == "connector" else 1]
    events = [uuid4() for _ in range(100 if limit == "connector" else 1000)]
    params = {"t": UUID(filler["tenant_id"]), "c": UUID(filler["connector_id"]), "events": events}
    async with admin_engine.begin() as c:
        await c.execute(
            text("""INSERT INTO integrations.webhook_receipts
            (tenant_id,connector_id,event_id,body_hash,kid,payload)
            SELECT :t,:c,e,repeat('b',64),'quota-fixture','{}'::jsonb
            FROM unnest(CAST(:events AS uuid[])) e"""),
            params,
        )
        await c.execute(
            text("""INSERT INTO integrations.ingress_jobs
            (tenant_id,connector_id,event_id)
            SELECT :t,:c,e FROM unnest(CAST(:events AS uuid[])) e"""),
            params,
        )
    try:
        body = producer.body()
        async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
            assert (await producer.post(client, body)).status_code == 429
            assert await receipt_count(admin_engine, body["event_id"]) == 0
            if limit == "connector":
                assert (await producer.post(client, producer.body(1), index=1)).status_code == 202
    finally:
        async with admin_engine.begin() as c:
            for table in ("ingress_jobs", "webhook_receipts"):
                await c.execute(
                    text(
                        f"DELETE FROM integrations.{table} WHERE tenant_id=:t "
                        "AND connector_id=:c AND event_id=ANY(CAST(:events AS uuid[]))"
                    ),
                    params,
                )


async def test_public_proxy_preserves_signed_body_and_enforces_ingress_limits(
    configured_cases, producer, admin_engine
):
    body = producer.body()
    raw, _ = producer.signed(body)
    async with httpx.AsyncClient(base_url="http://web", trust_env=False) as client:
        response = await producer.post(client, body)
        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
        assert (await producer.post(client, body)).status_code == 200
        path = f"/ingress/v1/{CASES[0]['tenant_id']}/{CASES[0]['connector_id']}"
        assert (await client.get(path)).status_code == 403
        assert (await producer.post(client, producer.body(), raw=b"x" * 16385)).status_code == 413
    async with admin_engine.connect() as c:
        assert (
            await c.scalar(
                text("SELECT body_hash FROM integrations.webhook_receipts WHERE event_id=:e"),
                {"e": UUID(body["event_id"])},
            )
            == hashlib.sha256(raw).hexdigest()
        )
