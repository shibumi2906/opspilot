"""Trusted execution context; database clock and row locks are authoritative."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opspilot.config import Settings
from opspilot.tenancy.context import require_tenant


@dataclass(frozen=True)
class Fence:
    run: UUID
    owner: UUID
    epoch: int


_current: ContextVar[Fence | None] = ContextVar("execution_fence", default=None)
_execution_engine: ContextVar[AsyncEngine | None] = ContextVar("execution_engine", default=None)


def current_engine() -> AsyncEngine | None:
    return _execution_engine.get()


def current_fence() -> Fence | None:
    return _current.get()


@contextmanager
def fence_scope(fence: Fence | None) -> Iterator[None]:
    token = _current.set(fence)
    try:
        yield
    finally:
        _current.reset(token)


async def acquire(conn: AsyncConnection, run: UUID, owner: UUID, seconds: float) -> Fence | None:
    await conn.execute(
        text("""INSERT INTO workflow.run_execution_leases(tenant_id,run_id)
      VALUES(:t,:r) ON CONFLICT DO NOTHING"""),
        {"t": require_tenant(), "r": run},
    )
    row = (
        await conn.execute(
            text("""UPDATE workflow.run_execution_leases SET owner=:o,
      epoch=epoch+1,lease_until=clock_timestamp()+:s*interval '1 second'
      WHERE tenant_id=:t AND run_id=:r AND lease_until<=clock_timestamp()
      RETURNING epoch"""),
            {"t": require_tenant(), "r": run, "o": owner, "s": seconds},
        )
    ).one_or_none()
    return Fence(run, owner, row[0]) if row else None


async def heartbeat(engine: AsyncEngine, fence: Fence, seconds: float) -> bool:
    async with engine.begin() as conn:
        # Read the clock only after acquiring the row: a blocked UPDATE predicate can be old.
        await conn.execute(
            text("""SELECT epoch FROM workflow.run_execution_leases
          WHERE tenant_id=:t AND run_id=:r AND owner=:o AND epoch=:e FOR UPDATE"""),
            {"t": require_tenant(), "r": fence.run, "o": fence.owner, "e": fence.epoch},
        )
        return bool(
            (
                await conn.execute(
                    text("""UPDATE workflow.run_execution_leases SET
          lease_until=clock_timestamp()+:s*interval '1 second' WHERE tenant_id=:t AND run_id=:r
          AND owner=:o AND epoch=:e AND lease_until>clock_timestamp() RETURNING epoch"""),
                    {
                        "s": seconds,
                        "t": require_tenant(),
                        "r": fence.run,
                        "o": fence.owner,
                        "e": fence.epoch,
                    },
                )
            ).one_or_none()
        )


async def release(engine: AsyncEngine, fence: Fence) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("""UPDATE workflow.run_execution_leases SET owner=NULL,
          lease_until=clock_timestamp()
          WHERE tenant_id=:t AND run_id=:r AND owner=:o AND epoch=:e
          AND NOT EXISTS (SELECT 1 FROM workflow.command_jobs j WHERE j.tenant_id=:t
            AND j.run_id=:r AND j.status='running' AND j.claim_owner=:o AND j.claim_epoch=:e)"""),
            {"t": require_tenant(), "r": fence.run, "o": fence.owner, "e": fence.epoch},
        )


async def pulse(
    engine: AsyncEngine, fence: Fence, settings: Settings, task: asyncio.Task[object]
) -> None:
    try:
        while True:
            await asyncio.sleep(settings.worker_heartbeat_seconds)
            if not await heartbeat(engine, fence, settings.worker_lease_seconds):
                from opspilot.observability.client import count

                count("lease_losses", "jobs")
                task.cancel()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        # Partition: abandon work immediately, then let DB expiry/reaper transfer ownership.
        task.cancel()


@asynccontextmanager
async def execution_lease(
    engine: AsyncEngine, run: UUID, settings: Settings, fence: Fence | None = None
) -> AsyncIterator[Fence]:
    existing = current_fence()
    if existing is not None:
        if existing.run != run:
            raise RuntimeError("Execution scope cannot change run")
        yield existing
        return
    if fence is None:
        async with asyncio.timeout(settings.worker_lease_seconds + 10):
            while fence is None:
                from opspilot.runtime.jobs import reap

                await reap(engine, run)
                async with engine.begin() as conn:
                    fence = await acquire(conn, run, uuid4(), settings.worker_lease_seconds)
                if fence is None:
                    await asyncio.sleep(0.1)
    task = asyncio.current_task()
    assert task is not None
    with fence_scope(fence):
        engine_token = _execution_engine.set(engine)
        beat = asyncio.create_task(pulse(engine, fence, settings, task))
        try:
            yield fence
        finally:
            beat.cancel()
            with suppress(asyncio.CancelledError):
                await beat
            try:
                await release(engine, fence)
            finally:
                _execution_engine.reset(engine_token)


async def ensure_current(settings: Settings) -> None:
    """Stop dispatch before the next heartbeat; reuse this execution's owned engine."""
    fence = current_fence()
    if fence is None:
        return  # Pure Runtime unit probes have no worker or database side effects.
    from opspilot.db.engine import create_engine

    owned_engine = _execution_engine.get()
    engine = owned_engine or create_engine(settings.database_url("workflow"))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT workflow.check_fence(:r)"), {"r": fence.run})
    finally:
        if owned_engine is None:
            await engine.dispose()
