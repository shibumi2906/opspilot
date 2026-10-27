import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from opspilot.auth.context import AuthError
from opspilot.auth.oidc import digest
from opspilot.auth.store import IdentityStore


async def test_idle_expiry_polling_parallel_limit_and_disable(integration_settings, admin_engine):
    store = IdentityStore(integration_settings)
    subject = "security-" + str(uuid4())
    try:
        first = await store.new_session(subject, "")
        user = await store.authenticate(first)
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET last_seen_at=clock_timestamp()-interval "
                    "'60 seconds' WHERE token_hash=:h"
                ),
                {"h": digest(first)},
            )
            before = await conn.scalar(
                text("SELECT last_seen_at FROM identity.sessions WHERE token_hash=:h"),
                {"h": digest(first)},
            )
        await store.authenticate(first)
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT last_seen_at FROM identity.sessions WHERE token_hash=:h"),
                    {"h": digest(first)},
                )
                == before
            )
        await store.authenticate(first, touch=True)
        async with admin_engine.begin() as conn:
            after = await conn.scalar(
                text("SELECT last_seen_at FROM identity.sessions WHERE token_hash=:h"),
                {"h": digest(first)},
            )
            assert after > before
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET last_seen_at=clock_timestamp()-interval "
                    "'2 hours' WHERE token_hash=:h"
                ),
                {"h": digest(first)},
            )
        with pytest.raises(AuthError):
            await store.authenticate(first, touch=True)
        for _ in range(5):
            await store.new_session(subject, "")
        assert len(await store.sessions(user.user_id)) == integration_settings.session_max_parallel
        raw = await store.new_session(subject, "")
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("UPDATE identity.users SET disabled_at=clock_timestamp() WHERE id=:u"),
                {"u": user.user_id},
            )
        with pytest.raises(AuthError):
            await store.authenticate(raw)
        with pytest.raises(AuthError):
            await store.new_session(subject, "")
    finally:
        await store.engine.dispose()


async def test_durable_budget_serializes_concurrent_requests(integration_settings):
    store = IdentityStore(integration_settings)
    key = "security-budget-" + str(uuid4())
    try:

        async def attempt():
            try:
                await store.consume_budget(key, 3, window=3600)
                return True
            except AuthError as exc:
                assert exc.status == 429
                return False

        assert sum(await asyncio.gather(*(attempt() for _ in range(12)))) == 3
    finally:
        await store.engine.dispose()


async def test_revocation_is_user_scoped(integration_settings):
    store = IdentityStore(integration_settings)
    try:
        raw1 = await store.new_session("security-one-" + str(uuid4()), "")
        raw2 = await store.new_session("security-two-" + str(uuid4()), "")
        one, two = await store.authenticate(raw1), await store.authenticate(raw2)
        await store.revoke_sessions(one.user_id, session=two.session_id, reason="test")
        await store.authenticate(raw2)
        await store.revoke_sessions(one.user_id, reason="test")
        with pytest.raises(AuthError):
            await store.authenticate(raw1)
        await store.authenticate(raw2)
    finally:
        await store.engine.dispose()


async def test_run_quota_is_atomic_and_preserves_idempotency(integration_settings, admin_engine):
    from uuid import NAMESPACE_URL, uuid5

    from sqlalchemy.exc import DBAPIError

    from opspilot.agent.service import run_investigation
    from opspilot.auth.context import Principal, auth_scope
    from opspilot.tenancy.context import DEMO_TENANT

    # Independent subject keeps this test separate from stage scenario actors.
    store = IdentityStore(integration_settings)
    try:
        subject = "quota-" + str(uuid4())
        await store.new_session(subject, "")
        user = uuid5(NAMESPACE_URL, integration_settings.oidc_issuer + "|" + subject)
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO identity.tenant_memberships VALUES(:t,:u,'operator')"),
                {"t": DEMO_TENANT, "u": user},
            )
        settings = integration_settings.model_copy(update={"max_actor_active_runs": 1})
        request_id = uuid4()
        with auth_scope(Principal(user, DEMO_TENANT, frozenset({"operator"}), uuid4())):
            first = await run_investigation(
                settings, "Investigate GreenShop", client_request_id=request_id, queued_only=True
            )
            replay = await run_investigation(
                settings, "Investigate GreenShop", client_request_id=request_id, queued_only=True
            )
            assert first["run_id"] == replay["run_id"]
            with pytest.raises(DBAPIError) as exc:
                await run_investigation(settings, "Another investigation", queued_only=True)
            assert exc.value.orig.sqlstate == "P0001"
            assert str(exc.value.orig).splitlines()[0] == "RUN_ADMISSION_LIMIT"
    finally:
        await store.engine.dispose()


async def test_admin_disable_and_revoke_respect_tenant_identity_scope(
    integration_settings, admin_engine
):
    import os

    import httpx

    from opspilot.auth.http import csrf
    from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
    from tests.auth_helpers import session_client

    store = IdentityStore(integration_settings)
    subject = "admin-security-" + str(uuid4())
    try:
        raw = await store.new_session(subject, "")
        actor = await store.authenticate(raw)
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO identity.tenant_memberships VALUES(:t,:u,'operator')"),
                {"t": DEMO_TENANT, "u": actor.user_id},
            )
        await store.select_tenant(actor, DEMO_TENANT)
        async with (
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as admin,
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as target,
        ):
            await session_client(admin, integration_settings, "admin")
            target.cookies.set("opspilot_session", raw)
            target.headers.update(
                {
                    "Origin": integration_settings.app_origin,
                    "X-CSRF-Token": csrf(integration_settings, raw),
                }
            )
            assert (await target.get("/auth/me")).status_code == 200
            endpoint = f"/api/v2/admin/users/{actor.user_id}"
            assert (
                await admin.put(endpoint + "/status", json={"enabled": False})
            ).status_code == 200
            assert (await target.get("/auth/me")).status_code == 401
            with pytest.raises(AuthError):
                await store.new_session(subject, "")
            assert (
                await admin.put(endpoint + "/status", json={"enabled": True})
            ).status_code == 200
            fresh = await store.new_session(subject, "")
            assert (await admin.post(endpoint + "/sessions/revoke-all")).status_code == 200
            with pytest.raises(AuthError):
                await store.authenticate(fresh)
            # Adding a foreign tenant prevents a tenant admin from global account operations.
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO identity.tenant_memberships VALUES(:t,:u,'operator')"),
                    {"t": SECOND_TENANT, "u": actor.user_id},
                )
            assert (
                await admin.put(endpoint + "/status", json={"enabled": False})
            ).status_code == 404
    finally:
        await store.engine.dispose()
