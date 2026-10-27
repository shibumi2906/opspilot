"""PostgreSQL commands. One worker owns a session advisory lock until F06."""

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


async def claim(
    engine: AsyncEngine, run_id: UUID | None = None, seconds: float = 30
) -> dict[str, Any] | None:
    from opspilot.runtime.fencing import acquire

    async with engine.begin() as conn:
        row = (
            (
                await conn.execute(
                    text("""SELECT * FROM workflow.command_jobs j
          WHERE tenant_id=:t AND status='pending' AND available_at<=clock_timestamp()
          AND (CAST(:r AS uuid) IS NULL OR run_id=:r)
          AND NOT EXISTS(SELECT 1 FROM workflow.run_execution_leases l WHERE l.tenant_id=j.tenant_id
            AND l.run_id=j.run_id AND l.lease_until>clock_timestamp())
          ORDER BY created_at,id LIMIT 1"""),
                    {"t": require_tenant(), "r": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        fence = await acquire(conn, row["run_id"], uuid4(), seconds)
        if fence is None:
            return None
        job = dict(row)
        job.update(attempts=row["attempts"] + 1, claim_owner=fence.owner, claim_epoch=fence.epoch)
        await conn.execute(
            text("""UPDATE workflow.command_jobs SET status='running',
          attempts=:a,claim_owner=:o,claim_epoch=:e,error_code=NULL
          WHERE id=:id AND tenant_id=:t"""),
            {
                "a": job["attempts"],
                "o": fence.owner,
                "e": fence.epoch,
                "id": row["id"],
                "t": require_tenant(),
            },
        )
        return job


async def finish(engine: AsyncEngine, job: dict[str, Any], *, failed: bool = False) -> None:
    dead = failed and job["attempts"] >= 5
    async with engine.begin() as conn:
        await conn.execute(text("SELECT workflow.check_fence(:r)"), {"r": job["run_id"]})
        changed = await conn.execute(
            text("""UPDATE workflow.command_jobs SET status=:status,
          available_at=clock_timestamp()+:delay*interval '1 second',
          finished_at=CASE WHEN :finished THEN clock_timestamp() ELSE NULL END,error_code=:error
          WHERE id=:id AND tenant_id=:t AND status='running' AND claim_owner=:o AND claim_epoch=:e
          RETURNING id"""),
            {
                "status": "dead" if dead else "pending" if failed else "done",
                "delay": min(60, 2 ** job["attempts"]),
                "finished": dead or not failed,
                "error": "COMMAND_DEAD_LETTER" if dead else "COMMAND_RETRY" if failed else None,
                "id": job["id"],
                "t": require_tenant(),
                "o": job["claim_owner"],
                "e": job["claim_epoch"],
            },
        )
        if changed.one_or_none() is None:
            raise RuntimeError("STALE_COMMAND_CLAIM")
        if dead:
            await conn.execute(
                text("""UPDATE workflow.agent_runs SET status='needs_attention',
              error='{"code":"COMMAND_DEAD_LETTER","message":"Worker retries exhausted"}'::jsonb
              WHERE id=:r AND tenant_id=:t AND status IN ('queued','running')"""),
                {"r": job["run_id"], "t": require_tenant()},
            )


async def reap(engine: AsyncEngine, run_id: UUID | None = None) -> int:
    # Ownership row first, then jobs: all execution writes use the same lock order.
    async with engine.begin() as conn:
        rows = (
            (
                await conn.execute(
                    text("""SELECT l.* FROM workflow.run_execution_leases l
          WHERE l.tenant_id=:t AND l.owner IS NOT NULL AND l.lease_until<=clock_timestamp()
          AND (CAST(:r AS uuid) IS NULL OR l.run_id=:r) FOR UPDATE SKIP LOCKED"""),
                    {"t": require_tenant(), "r": run_id},
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            owner = uuid4()
            epoch = row["epoch"] + 1
            await conn.execute(
                text("""UPDATE workflow.run_execution_leases SET owner=:o,epoch=:e,
              lease_until=clock_timestamp()+interval '30 seconds'
              WHERE tenant_id=:t AND run_id=:r"""),
                {"o": owner, "e": epoch, "t": require_tenant(), "r": row["run_id"]},
            )
            for key, value in {
                "execution_owner": owner,
                "execution_epoch": epoch,
                "execution_run": row["run_id"],
            }.items():
                await conn.execute(
                    text("SELECT set_config(:k,:v,true)"), {"k": "app." + key, "v": str(value)}
                )
            jobs = (
                (
                    await conn.execute(
                        text("""UPDATE workflow.command_jobs SET
              status=CASE WHEN attempts>=5 THEN 'dead' ELSE 'pending' END,
              error_code=CASE WHEN attempts>=5 THEN 'COMMAND_DEAD_LETTER' ELSE 'LEASE_EXPIRED' END,
              available_at=clock_timestamp()+LEAST(60,power(2,attempts))*interval '1 second',
              finished_at=CASE WHEN attempts>=5 THEN clock_timestamp() ELSE NULL END
              WHERE tenant_id=:t AND run_id=:r AND status='running' AND claim_epoch=:e
              RETURNING status"""),
                        {"t": require_tenant(), "r": row["run_id"], "e": row["epoch"]},
                    )
                )
                .scalars()
                .all()
            )
            if "dead" in jobs:
                await conn.execute(
                    text("""UPDATE workflow.agent_runs SET status='needs_attention',
                  error='{"code":"COMMAND_DEAD_LETTER","message":"Worker retries exhausted"}'::jsonb
                  WHERE tenant_id=:t AND id=:r AND status IN ('queued','running')"""),
                    {"t": require_tenant(), "r": row["run_id"]},
                )
            await conn.execute(
                text("""UPDATE workflow.run_execution_leases SET owner=NULL,
              lease_until=clock_timestamp() WHERE tenant_id=:t AND run_id=:r"""),
                {"t": require_tenant(), "r": row["run_id"]},
            )
        return len(rows)
