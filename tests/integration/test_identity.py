from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from opspilot.auth.context import AuthError
from opspilot.auth.oidc import digest
from opspilot.auth.store import IdentityStore
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client


async def test_sessions_csrf_switch_logout_revocation(integration_settings, admin_engine):
    import os

    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        assert (await client.get("/auth/me")).status_code == 401
        raw, user = await session_client(client, integration_settings)
        assert (await client.get("/auth/me")).json()["tenant_id"] == str(DEMO_TENANT)
        assert (
            await client.post(
                "/auth/tenant",
                json={"tenant_id": str(SECOND_TENANT)},
                headers={"Origin": "https://evil.invalid"},
            )
        ).status_code == 403
        assert (
            await client.post(
                "/auth/tenant",
                json={"tenant_id": str(SECOND_TENANT)},
                headers={"X-CSRF-Token": "bad"},
            )
        ).status_code == 403
        assert (
            await client.post("/auth/tenant", json={"tenant_id": str(uuid4())})
        ).status_code == 403
        assert (
            await client.post("/auth/tenant", json={"tenant_id": str(SECOND_TENANT)})
        ).status_code == 200
        assert (await client.get("/auth/me")).json()["tenant_id"] == str(SECOND_TENANT)
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET expires_at=clock_timestamp()-interval "
                    "'1 second' WHERE token_hash=:h"
                ),
                {"h": digest(raw)},
            )
        assert (await client.get("/auth/me")).status_code == 401
        await session_client(client, integration_settings)
        assert (await client.post("/auth/logout")).status_code == 200
        assert (await client.get("/auth/me")).status_code == 401


async def test_login_one_time_state_binding_and_session_fixation(integration_settings):
    store = IdentityStore(integration_settings)
    try:
        state, binding, _, _ = await store.new_login()
        with pytest.raises(AuthError):
            await store.consume_login(state, "wrong-browser")
        await store.consume_login(state, binding)
        with pytest.raises(AuthError):
            await store.consume_login(state, binding)
        old = await store.new_session("unassigned-fixture", "")
        new = await store.new_session("unassigned-fixture", old)
        assert old != new
        with pytest.raises(AuthError):
            await store.authenticate(old)
        assert (await store.memberships((await store.authenticate(new)).user_id)) == []
    finally:
        await store.engine.dispose()


async def test_operator_cannot_approve_and_membership_revocation(
    integration_settings, admin_engine
):
    import os

    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        _, user = await session_client(client, integration_settings, "operator")
        assert (
            await client.post(
                f"/api/v2/runs/{uuid4()}/decision",
                json={"action_id": str(uuid4()), "decision": "approve"},
            )
        ).status_code == 403
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM identity.tenant_memberships WHERE user_id=:u AND tenant_id=:t"),
                {"u": user, "t": DEMO_TENANT},
            )
        try:
            assert (
                await client.post(
                    "/api/v2/runs",
                    json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
                )
            ).status_code == 403
        finally:
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO identity.tenant_memberships VALUES (:t,:u,'operator')"),
                    {"t": DEMO_TENANT, "u": user},
                )


async def test_self_approval_default_denied_demo_exception_persisted(integration_settings):
    import asyncio
    import os
    from uuid import UUID

    from opspilot.auth.context import auth_scope
    from opspilot.contracts.api import CreateRun, Decision
    from opspilot.runtime.run_service import RunService

    store = IdentityStore(integration_settings)
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as client:
        raw, _ = await session_client(client, integration_settings)
        user = await store.authenticate(raw)
    service = RunService(
        integration_settings.model_copy(update={"allow_demo_self_approval": False})
    )
    try:
        with auth_scope(user):
            created = await service.create(
                CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
            )
            await asyncio.gather(*service.tasks)
            run = UUID(created["run_id"])
            snapshot = await service.snapshot(run)
            choice = Decision(action_id=UUID(snapshot["action"]["action_id"]), decision="approve")
            with pytest.raises(AuthError, match="SELF_APPROVAL_FORBIDDEN"):
                await service.decide(run, choice)
            service.settings = integration_settings.model_copy(
                update={"allow_demo_self_approval": True}
            )
            await service.decide(run, choice)
            await asyncio.gather(*service.tasks)
            async with service.engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT decided_by,self_approval_exception FROM workflow.approvals "
                            "WHERE action_id=:id"
                        ),
                        {"id": choice.action_id},
                    )
                ).one()
                assert row == (user.user_id, True)
    finally:
        await service.close()
        await store.engine.dispose()


async def test_identity_gateway_is_not_domain_owner_or_rls_bypass(integration_settings):
    from sqlalchemy.exc import DBAPIError

    from opspilot.db.engine import create_engine

    engine = create_engine(integration_settings.database_url("identity"))
    try:
        async with engine.connect() as conn:
            assert (
                await conn.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            ).one() == (False, False)
        for statement in [
            "SELECT * FROM domain.customers",
            "ALTER TABLE identity.sessions DISABLE ROW LEVEL SECURITY",
        ]:
            async with engine.begin() as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(text(statement))
    finally:
        await engine.dispose()
