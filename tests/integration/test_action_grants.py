"""F09 real DB/MCP authorization, immutable revisions and human command races."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from opspilot.agent.service import run_investigation
from opspilot.auth.context import AuthError
from opspilot.auth.service_context import action_scope
from opspilot.contracts.api import Decision
from opspilot.contracts.tools import CreateTicketArgs
from opspilot.db.engine import create_engine
from opspilot.db.models_domain import Ticket
from opspilot.db.models_workflow import Action
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.actions import expire_approvals, payload_hash
from opspilot.runtime.fencing import execution_lease
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.security.grants import issue
from opspilot.security.keys import grant_keys
from tests.auth_helpers import session_client


async def pending(settings):
    value = await run_investigation(settings, "Investigate GreenShop", mode="scripted")
    return CreateTicketArgs(
        run_id=value["run_id"], action_id=value["action_id"], arguments=value["proposed_action"]
    )


async def approve(settings, args):
    service = RunService(settings)
    try:
        await service.decide(
            args.run_id, Decision(action_id=args.action_id, decision="approve", expected_version=1)
        )
    finally:
        await service.close()


async def rpc(settings, args):
    with action_scope(
        str(args.run_id), str(args.action_id), payload_hash(args.arguments.model_dump(mode="json"))
    ):
        async with MCPClient(settings).session() as (session, _):
            return await MCPClient.call(session, "create_ticket", args.model_dump(mode="json"))


async def count(engine, args):
    async with engine.connect() as conn:
        return await conn.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.originating_action_id == args.action_id)
        )


@pytest.mark.parametrize(
    "field",
    [
        "tenant",
        "run",
        "revision",
        "actor",
        "approver",
        "payload_hash",
        "epoch",
        "tool",
        "aud",
        "iss",
        "jti",
        "exp",
        "kid",
        "missing",
    ],
)
async def test_grant_tampering_never_writes(integration_settings, admin_engine, monkeypatch, field):
    settings = integration_settings
    args = await pending(settings)
    await approve(settings, args)
    engine = create_engine(settings.database_url("workflow"))
    try:
        async with execution_lease(engine, args.run_id, settings):
            token = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                },
            )
            claims = jwt.decode(token, options={"verify_signature": False})
            kid = jwt.get_unverified_header(token)["kid"]
            if field in ["tenant", "run", "revision", "actor", "approver", "jti"]:
                claims[field] = str(uuid4())
            if field == "payload_hash":
                claims[field] = "0" * 64
            if field == "epoch":
                claims[field] += 1
            if field in ["tool", "aud", "iss"]:
                claims[field] = "untrusted"
            if field == "exp":
                claims[field] = claims["iat"] - 1
            if field == "kid":
                kid = "current"
            if field == "kid":
                key = await asyncio.to_thread(
                    Path(settings.service_private_dir, "current.pem").read_bytes
                )
            else:
                # Mutate claims under the actual issuer key, including manager mode.
                # A missing file or unrelated lab signature would not test claim checks.
                reference, key = await asyncio.to_thread(
                    grant_keys(settings).signing_key, kid.split(":")[0]
                )
                assert reference.kid == kid
            fake = jwt.encode(
                claims,
                key,
                algorithm="EdDSA",
                headers={"kid": kid, "typ": "opspilot-execution+jwt"},
            )

            async def forged(*args, **kwargs):
                if field == "missing":
                    raise AuthError("GRANT_REQUIRED")
                return fake

            monkeypatch.setattr("opspilot.mcp_client.client.issue", forged)
            result = await rpc(settings, args)
            assert not result.ok and result.error.code in {"GRANT_REQUIRED", "GRANT_INVALID"}
            assert await count(admin_engine, args) == 0
    finally:
        await engine.dispose()


async def test_grant_replay_is_atomic_and_epoch_bound(
    integration_settings, admin_engine, monkeypatch
):
    settings = integration_settings
    args = await pending(settings)
    await approve(settings, args)
    engine = create_engine(settings.database_url("workflow"))
    try:
        async with execution_lease(engine, args.run_id, settings):
            old = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                },
            )
        async with execution_lease(engine, args.run_id, settings):

            async def stale(*args, **kwargs):
                return old

            monkeypatch.setattr("opspilot.mcp_client.client.issue", stale)
            denied = await rpc(settings, args)
            assert not denied.ok and denied.error.code == "GRANT_INVALID"
            assert await count(admin_engine, args) == 0
            token = await issue(
                settings,
                {
                    "run": str(args.run_id),
                    "action": str(args.action_id),
                    "hash": payload_hash(args.arguments.model_dump(mode="json")),
                },
            )

            async def valid(*args, **kwargs):
                return token

            monkeypatch.setattr("opspilot.mcp_client.client.issue", valid)
            results = await asyncio.gather(*(rpc(settings, args) for _ in range(3)))
            assert all(r.ok for r in results)
            assert sum(not r.data["replayed"] for r in results) == 1
            assert await count(admin_engine, args) == 1
            async with admin_engine.connect() as conn:
                assert (
                    await conn.scalar(
                        text(
                            "SELECT count(*) FROM workflow.execution_grants "
                            "WHERE revision_id=:a AND consumed_at IS NOT NULL"
                        ),
                        {"a": args.action_id},
                    )
                    == 1
                )
    finally:
        await engine.dispose()


async def test_revision_payload_cannot_mutate(integration_settings, admin_engine):
    args = await pending(integration_settings)
    with pytest.raises(DBAPIError, match="IMMUTABLE_REVISION"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                update(Action).where(Action.id == args.action_id).values(arguments_hash="0" * 64)
            )
    assert await count(admin_engine, args) == 0


async def settle(service, run):
    async with asyncio.timeout(30):
        while True:
            value = await service.snapshot(run)
            if value["status"] not in {"queued", "running"}:
                return value
            await process_one(service, run)
            await asyncio.sleep(0.05)


async def test_revision_after_approval_requires_new_decision(integration_settings):
    import os

    settings = integration_settings
    service = RunService(settings)
    try:
        async with (
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as owner,
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as approver,
        ):
            await session_client(owner, settings, "operator")
            await session_client(approver, settings, "approver")
            r = await owner.post(
                "/api/v2/runs",
                json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
            )
            run = UUID(r.json()["run_id"])
            old = (await settle(service, run))["action"]
            path = f"/api/v2/runs/{run}/decision"
            choice = {"action_id": old["action_id"], "decision": "approve", "expected_version": 1}
            assert (
                await approver.post(path, json={**choice, "expected_version": True})
            ).status_code == 422
            assert (await approver.post(path, json=choice)).status_code == 202
            revision = f"/api/v2/actions/{old['logical_action_id']}/revisions"
            changed = {**old["arguments"], "title": "Human reviewed exact title"}
            assert (
                await owner.post(revision, json={"expected_version": 1, "arguments": changed})
            ).status_code == 201
            current = (await owner.get(f"/api/v2/runs/{run}")).json()["action"]
            assert current["action_id"] != old["action_id"] and current["expected_version"] == 2
            assert current["approval_status"] == "pending"
            assert (
                await owner.post(revision, json={"expected_version": 1, "arguments": changed})
            ).json()["action"]["action_id"] == current["action_id"]
            assert (await approver.post(path, json=choice)).status_code == 409
            assert (
                await approver.post(
                    path,
                    json={
                        "action_id": current["action_id"],
                        "expected_version": 1,
                        "decision": "approve",
                    },
                )
            ).status_code == 409
            assert (
                await approver.post(
                    path,
                    json={
                        "action_id": current["action_id"],
                        "expected_version": 2,
                        "decision": "approve",
                    },
                )
            ).status_code == 202
            done = await settle(service, run)
            assert (
                done["outcome"] == "actions_verified"
                and done["action"]["arguments"]["title"] == changed["title"]
            )
            assert (
                await owner.post(
                    revision,
                    json={
                        "expected_version": 2,
                        "arguments": {**changed, "title": "second effect"},
                    },
                )
            ).status_code == 409
    finally:
        await service.close()


async def test_expiry_decision_race_uses_db_clock(integration_settings, admin_engine):
    settings = integration_settings.model_copy(update={"approval_ttl_seconds": 1})
    args = await pending(settings)
    await asyncio.sleep(1.05)
    service = RunService(settings)
    try:
        with pytest.raises(AuthError) as exc:
            await service.decide(
                args.run_id,
                Decision(action_id=args.action_id, decision="approve", expected_version=1),
            )
        assert exc.value.status == 410
        await expire_approvals(service)
        result = await settle(service, args.run_id)
        assert result["status"] == "completed" and result["action"]["approval_status"] == "expired"
        assert await count(admin_engine, args) == 0
    finally:
        await service.close()


async def test_revocation_and_exact_replay_remain_terminal(integration_settings, admin_engine):
    import os

    settings = integration_settings
    service = RunService(settings)
    try:
        async with (
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as owner,
            httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as approver,
        ):
            await session_client(owner, settings, "operator")
            await session_client(approver, settings, "approver")
            response = await owner.post(
                "/api/v2/runs",
                json={"request": "Investigate GreenShop", "client_request_id": str(uuid4())},
            )
            run = UUID(response.json()["run_id"])
            card = (await settle(service, run))["action"]
            choice = {"action_id": card["action_id"], "decision": "approve", "expected_version": 1}
            assert (
                await approver.post(f"/api/v2/runs/{run}/decision", json=choice)
            ).status_code == 202
            url = f"/api/v2/actions/{card['action_id']}/revoke"
            assert (await owner.post(url, json={"expected_version": 1})).status_code == 403
            assert (await approver.post(url, json={"expected_version": 1})).status_code == 200
            assert (await approver.post(url, json={"expected_version": 1})).status_code == 200
            result = await settle(service, run)
            assert (
                result["action"]["approval_status"] == "revoked" and result["outcome"] == "partial"
            )
            args = CreateTicketArgs(
                run_id=run, action_id=card["action_id"], arguments=card["arguments"]
            )
            assert await count(admin_engine, args) == 0
    finally:
        await service.close()


async def test_decision_blocked_on_row_cannot_cross_expiry(integration_settings, admin_engine):
    settings = integration_settings.model_copy(update={"approval_ttl_seconds": 1})
    args = await pending(settings)
    service = RunService(settings)
    try:
        async with admin_engine.connect() as conn:
            transaction = await conn.begin()
            await conn.execute(
                text("SELECT id FROM workflow.approvals WHERE action_id=:a FOR UPDATE"),
                {"a": args.action_id},
            )
            deciding = asyncio.create_task(
                service.decide(
                    args.run_id,
                    Decision(action_id=args.action_id, expected_version=1, decision="approve"),
                )
            )
            await asyncio.sleep(1.1)
            await transaction.commit()
            with pytest.raises(AuthError) as error:
                await deciding
            assert error.value.status == 410
        await expire_approvals(service)
        assert (await settle(service, args.run_id))["action"]["approval_status"] == "expired"
        assert await count(admin_engine, args) == 0
    finally:
        await service.close()


async def test_new_revision_expiry_rearms_old_completed_resume(integration_settings, admin_engine):
    from opspilot.db.models_workflow import Approval, LogicalAction
    from opspilot.runtime.actions import new_revision
    from opspilot.runtime.jobs import enqueue
    from opspilot.tenancy.session import TenantSession

    settings = integration_settings
    args = await pending(settings)
    service = RunService(settings)
    try:
        async with execution_lease(service.engine, args.run_id, settings):
            async with TenantSession(service.engine) as session, session.begin():
                old = await session.get(Action, args.action_id)
                assert old is not None
                approval = await session.scalar(
                    select(Approval).where(Approval.action_id == old.id)
                )
                assert approval is not None
                approval.decision = "superseded"
                old.superseded_at = await session.scalar(select(func.clock_timestamp()))
                logical = await session.get(LogicalAction, old.logical_action_id)
                assert logical is not None
                logical.version += 1
                logical.current_revision_id = uuid4()
                await session.flush()
                revised = await new_revision(
                    session,
                    logical,
                    old.arguments,
                    settings.model_copy(update={"approval_ttl_seconds": 1}),
                )
                revision_id = revised.id
                await enqueue(session, args.run_id, "resume", old.id)
                await session.execute(
                    text(
                        "UPDATE workflow.command_jobs SET status='done' "
                        "WHERE run_id=:r AND kind='resume'"
                    ),
                    {"r": args.run_id},
                )
        await asyncio.sleep(1.05)
        await expire_approvals(service)
        async with admin_engine.connect() as conn:
            job = (
                await conn.execute(
                    text(
                        "SELECT status,action_id FROM workflow.command_jobs "
                        "WHERE run_id=:r AND kind='resume'"
                    ),
                    {"r": args.run_id},
                )
            ).one()
            assert job.status == "pending" and job.action_id == revision_id
        result = await settle(service, args.run_id)
        assert result["status"] == "completed" and result["action"]["approval_status"] == "expired"
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    select(func.count())
                    .select_from(Ticket)
                    .where(Ticket.originating_action_id == revision_id)
                )
                == 0
            )
    finally:
        await service.close()
