"""Independent durable worker; session singleton, no lease/multiworker claim."""

import asyncio
import signal
from uuid import UUID

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.contracts.api import CreateRun
from opspilot.db.models_workflow import AgentRun
from opspilot.runtime.jobs import claim, finish
from opspilot.runtime.recovery import recover
from opspilot.runtime.run_service import RunService
from opspilot.telemetry import configure
from opspilot.tenancy.context import tenant_scope
from opspilot.tenancy.session import TenantSession

WORKER_LOCK = 1801202605


async def process_one(service: RunService, run_id: UUID | None = None) -> bool:
    job = await claim(service.engine, run_id)
    if job is None:
        return False
    try:
        async with TenantSession(service.engine) as session:
            run = await session.get(AgentRun, job["run_id"])
            if run is None:
                raise RuntimeError("Command run missing")
        if run.status == "queued" and job["kind"] == "start":
            await service.execute(
                run.id, CreateRun(request=run.request, client_request_id=run.client_request_id)
            )
        elif run.status in {"running", "waiting_for_approval"}:
            await recover(service, run.id)
        await finish(service.engine, job)
    except Exception:
        # No raw provider details persist. Cancellation leaves a running job for restart.
        await finish(service.engine, job, failed=True)
    return True


async def serve(settings: Settings, stop: asyncio.Event) -> None:
    service = RunService(settings)
    guard = await service.engine.connect()
    try:
        if not await guard.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}):
            raise RuntimeError("Only one worker process is supported until F06")
        await guard.commit()
        for tenant in settings.recovery_tenants:
            with tenant_scope(tenant):
                async with service.engine.connect() as conn:
                    interrupted = (
                        (
                            await conn.execute(
                                text("""SELECT id,run_id,attempts
                        FROM workflow.command_jobs WHERE tenant_id=:t AND status='running'"""),
                                {"t": tenant},
                            )
                        )
                        .mappings()
                        .all()
                    )
                for job in interrupted:
                    await finish(service.engine, dict(job), failed=True)
        while not stop.is_set():
            # A failed guard connection stops the process; never continue after losing singleton.
            await guard.execute(text("SELECT 1"))
            await guard.commit()
            worked = False
            for tenant in settings.recovery_tenants:
                if stop.is_set():
                    break
                with tenant_scope(tenant):
                    worked = await process_one(service) or worked
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), 0.25)
                except TimeoutError:
                    pass
    finally:
        # SIGTERM drains the active command before releasing ownership.
        await service.close()
        try:
            await guard.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK})
        finally:
            await guard.close()


async def main() -> None:
    settings = Settings()
    configure(settings, "opspilot-worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await serve(settings, stop)


if __name__ == "__main__":
    asyncio.run(main())
