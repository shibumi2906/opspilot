"""Real database and MCP compaction/replay/privacy checks. No destructive dev/MVP access."""

import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.db.engine import create_engine
from opspilot.runtime.fencing import execution_lease
from opspilot.security.lifecycle import RetentionPolicy, export, retain
from opspilot.tenancy.context import DEMO_ACTOR, DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client
from tests.integration.test_local_operations import count, rpc, setup_action


async def administrator(conn):
    return await conn.scalar(
        text(
            "SELECT user_id FROM identity.tenant_memberships "
            "WHERE tenant_id=:t AND role='admin' LIMIT 1"
        ),
        {"t": DEMO_TENANT},
    )


async def test_evidence_period_scrubs_projection_but_preserves_history(
    integration_settings, admin_engine
):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        args = await setup_action(integration_settings, admin_engine, engine, "create_ticket")
        async with execution_lease(engine, args.run_id, integration_settings):
            assert (await rpc(integration_settings, "create_ticket", args)).ok
        async with admin_engine.begin() as conn:
            actor = await administrator(conn)
            await conn.execute(
                text("""UPDATE workflow.agent_runs SET status='completed',
                  updated_at=clock_timestamp()-interval '45 days',
                  public_snapshot=jsonb_build_object('evidence',jsonb_build_object(
                    'private',jsonb_build_object('text','F17_EVIDENCE_SENTINEL'))),
                  tool_results=jsonb_build_object('body','F17_EVIDENCE_SENTINEL') WHERE id=:r"""),
                {"r": args.run_id},
            )
            preview = await retain(conn, DEMO_TENANT, actor, RetentionPolicy())
            candidate = next(r for r in preview["runs"] if r["run_id"] == str(args.run_id))
            assert not candidate["history"] and not candidate["audit"]
            await retain(
                conn,
                DEMO_TENANT,
                actor,
                RetentionPolicy(),
                apply=True,
                expected_preview=preview["preview_hash"],
            )
            row = (
                (
                    await conn.execute(
                        text("""SELECT r.request,r.tool_results,r.public_snapshot,
              s.projection FROM workflow.agent_runs r JOIN workflow.run_streams s
              ON s.tenant_id=r.tenant_id AND s.run_id=r.id WHERE r.id=:r"""),
                        {"r": args.run_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row["request"]
            assert "F17_EVIDENCE_SENTINEL" not in json.dumps(dict(row))
            assert await conn.scalar(
                text("SELECT arguments<>'{}'::jsonb FROM workflow.actions WHERE id=:a"),
                {"a": args.action_id},
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM workflow.run_events WHERE run_id=:r"),
                    {"r": args.run_id},
                )
                > 0
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", ["create_ticket", "add_ticket_comment", "notify_manager"])
async def test_compaction_preserves_receipt_and_blocks_replay(
    integration_settings, admin_engine, kind
):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        args = await setup_action(integration_settings, admin_engine, engine, kind)
        async with execution_lease(engine, args.run_id, integration_settings):
            assert (await rpc(integration_settings, kind, args)).ok
        before = await count(admin_engine, kind, args)
        async with admin_engine.begin() as conn:
            actor = await administrator(conn)
            await conn.execute(
                text("""INSERT INTO workflow.human_commands(tenant_id,run_id,command_id,payload)
                  VALUES(:t,:r,:c,jsonb_build_object('choice','F17_HUMAN_SENTINEL'))"""),
                {"t": DEMO_TENANT, "r": args.run_id, "c": uuid4()},
            )
            await conn.execute(
                text(
                    "UPDATE workflow.agent_runs SET status='completed',"
                    "updated_at=clock_timestamp()-interval '400 days',"
                    'tool_results=\'{"private":"F17_SENTINEL_SECRET"}\' WHERE id=:r'
                ),
                {"r": args.run_id},
            )
            preview = await retain(conn, DEMO_TENANT, actor, RetentionPolicy())
            assert str(args.run_id) in [r["run_id"] for r in preview["runs"]]
            assert (
                await conn.scalar(
                    text("SELECT tool_results->>'private' FROM workflow.agent_runs WHERE id=:r"),
                    {"r": args.run_id},
                )
                == "F17_SENTINEL_SECRET"
            )
            result = await retain(
                conn,
                DEMO_TENANT,
                actor,
                RetentionPolicy(),
                apply=True,
                expected_preview=preview["preview_hash"],
            )
            assert result["applied"]
            assert await conn.scalar(
                text(
                    "SELECT arguments='{}' AND revision_document='{}' "
                    "AND execution_result IS NULL FROM workflow.actions WHERE id=:a"
                ),
                {"a": args.action_id},
            )
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.deletion_tombstones "
                        "WHERE run_id=:r AND kind='operation'"
                    ),
                    {"r": args.run_id},
                )
                == 1
            )
            assert "F17_SENTINEL_SECRET" not in json.dumps(await export(conn, DEMO_TENANT, actor))
            command = await conn.scalar(
                text("SELECT payload FROM workflow.human_commands WHERE run_id=:r"),
                {"r": args.run_id},
            )
            assert set(command) == {"erased_payload_sha256"}
            assert len(command["erased_payload_sha256"]) == 64
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM workflow.run_events WHERE run_id=:r"),
                    {"r": args.run_id},
                )
                == 0
            )
        assert await count(admin_engine, kind, args) == before
        async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"]) as auditor:
            await session_client(auditor, integration_settings, "auditor")
            archived = await auditor.get(f"/api/v2/runs/{args.run_id}")
            assert archived.status_code == 200
            value = archived.json()
            assert value["retention"] == {
                "evidence_removed": True,
                "history_removed": True,
                "audit_removed": True,
            }
            assert not value["request"] and not value["evidence"]
            assert value["action"] is None and value["actions"] == []
            await session_client(auditor, integration_settings, "auditor", tenant=SECOND_TENANT)
            assert (await auditor.get(f"/api/v2/runs/{args.run_id}")).status_code == 404
        # Runtime SQL cannot resurrect the compacted run, even with a remembered command key.
        with pytest.raises(DBAPIError, match="RUN_COMPACTED"):
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE workflow.agent_runs SET status='queued' WHERE id=:r"),
                    {"r": args.run_id},
                )
        with pytest.raises(DBAPIError, match="RUN_COMPACTED"):
            async with execution_lease(engine, args.run_id, integration_settings):
                await rpc(integration_settings, kind, args)
        assert await count(admin_engine, kind, args) == before
    finally:
        await engine.dispose()


@pytest.mark.parametrize("protected", ["pending", "unknown", "active", "job", "lease"])
async def test_retention_preserves_protected_runs(integration_settings, admin_engine, protected):
    engine = create_engine(integration_settings.database_url("workflow"))
    try:
        args = await setup_action(integration_settings, admin_engine, engine, "create_ticket")
        async with admin_engine.begin() as conn:
            actor = await administrator(conn)
            await conn.execute(
                text(
                    "UPDATE workflow.agent_runs SET status=:s,"
                    "updated_at=clock_timestamp()-interval '400 days',"
                    "tool_results=jsonb_build_object('keep',true) "
                    "WHERE id=:r"
                ),
                {"r": args.run_id, "s": "running" if protected == "active" else "completed"},
            )
            if protected == "pending":
                # Replace the synthetic fixture before any grants/effects exist.
                await conn.execute(
                    text("DELETE FROM workflow.approvals WHERE action_id=:a"), {"a": args.action_id}
                )
                await conn.execute(
                    text(
                        "INSERT INTO workflow.approvals(id,tenant_id,action_id,decision) "
                        "VALUES(:id,:t,:a,'pending')"
                    ),
                    {"id": uuid4(), "t": DEMO_TENANT, "a": args.action_id},
                )
            elif protected == "unknown":
                await conn.execute(
                    text("UPDATE workflow.actions SET execution_status='unknown' WHERE id=:a"),
                    {"a": args.action_id},
                )
            elif protected == "job":
                await conn.execute(
                    text(
                        "INSERT INTO workflow.command_jobs(id,tenant_id,run_id,kind) "
                        "VALUES(:id,:t,:r,'start')"
                    ),
                    {"id": uuid4(), "t": DEMO_TENANT, "r": args.run_id},
                )
            elif protected == "lease":
                await conn.execute(
                    text(
                        "UPDATE workflow.run_execution_leases SET owner=:o,"
                        "lease_until=clock_timestamp()+interval '1 hour' WHERE run_id=:r"
                    ),
                    {"o": uuid4(), "r": args.run_id},
                )
            preview = await retain(conn, DEMO_TENANT, actor, RetentionPolicy())
            assert str(args.run_id) not in [r["run_id"] for r in preview["runs"]]
            assert (
                await conn.scalar(
                    text("SELECT tool_results->>'keep' FROM workflow.agent_runs WHERE id=:r"),
                    {"r": args.run_id},
                )
                == "true"
            )
            # Roll back synthetic protected work, so no live worker picks it up later.
            await conn.rollback()
    finally:
        await engine.dispose()


async def test_lifecycle_authorization_export_and_preview_cas(integration_settings, admin_engine):
    async with admin_engine.begin() as conn:
        actor = await administrator(conn)
        for tenant, user in [(DEMO_TENANT, DEMO_ACTOR), (SECOND_TENANT, uuid4())]:
            with pytest.raises(PermissionError):
                await export(conn, tenant, user)
        result = await export(conn, DEMO_TENANT, actor)
        other = set(
            (
                await conn.execute(
                    text("SELECT id::text FROM workflow.agent_runs WHERE tenant_id=:t"),
                    {"t": SECOND_TENANT},
                )
            ).scalars()
        )
        assert not other & {r["id"] for r in result["runs"]}
        assert all(
            set(r) == {"id", "status", "outcome", "created_at", "updated_at"}
            for r in result["runs"]
        )
        with pytest.raises(ValueError, match="Preview changed"):
            await retain(
                conn, DEMO_TENANT, actor, RetentionPolicy(), apply=True, expected_preview="forged"
            )
    runtime = create_engine(integration_settings.database_url("workflow"))
    try:
        async with runtime.begin() as conn:
            with pytest.raises(PermissionError):
                await export(conn, DEMO_TENANT, actor)
    finally:
        await runtime.dispose()
