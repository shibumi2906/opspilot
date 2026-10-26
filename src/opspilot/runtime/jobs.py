"""PostgreSQL commands. One worker owns a session advisory lock until F06."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.tenancy.context import require_tenant
from opspilot.tenancy.session import TenantSession


async def enqueue(
    session: TenantSession, run_id: UUID, kind: str, action_id: UUID | None = None
) -> None:
    # The caller owns the run/decision transaction; never commit here.
    await session.execute(
        text("""INSERT INTO workflow.command_jobs
        (id,tenant_id,run_id,kind,action_id) VALUES(:id,:tenant,:run,:kind,:action)
        ON CONFLICT(tenant_id,run_id,kind) DO NOTHING"""),
        {
            "id": uuid4(),
            "tenant": require_tenant(),
            "run": run_id,
            "kind": kind,
            "action": action_id,
        },
    )


async def claim(engine: AsyncEngine, run_id: UUID | None = None) -> dict[str, Any] | None:
    async with engine.begin() as conn:
        row = (
            (
                await conn.execute(
                    text("""UPDATE workflow.command_jobs SET
            status='running',attempts=attempts+1,error_code=NULL WHERE id=(
              SELECT id FROM workflow.command_jobs WHERE tenant_id=:tenant
              AND status='pending' AND available_at<=now()
              AND (CAST(:run AS uuid) IS NULL OR run_id=:run)
              ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING id,run_id,kind,action_id,attempts"""),
                    {"tenant": require_tenant(), "run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None


async def finish(engine: AsyncEngine, job: dict[str, Any], *, failed: bool = False) -> None:
    dead = failed and job["attempts"] >= 5
    async with engine.begin() as conn:
        await conn.execute(
            text("""UPDATE workflow.command_jobs SET status=:status,
            available_at=:available,finished_at=:finished,error_code=:error
            WHERE id=:id AND tenant_id=:tenant AND status='running'"""),
            {
                "status": "dead" if dead else "pending" if failed else "done",
                "available": datetime.now(UTC) + timedelta(seconds=min(60, 2 ** job["attempts"])),
                "finished": datetime.now(UTC) if dead or not failed else None,
                "error": "COMMAND_DEAD_LETTER" if dead else "COMMAND_RETRY" if failed else None,
                "id": job["id"],
                "tenant": require_tenant(),
            },
        )
        if dead:
            await conn.execute(
                text("""UPDATE workflow.agent_runs SET status='failed',
                error='{"code":"COMMAND_DEAD_LETTER","message":"Worker retries exhausted"}'::jsonb
                WHERE id=:id AND tenant_id=:tenant AND status IN ('queued','running')"""),
                {"id": job["run_id"], "tenant": require_tenant()},
            )
