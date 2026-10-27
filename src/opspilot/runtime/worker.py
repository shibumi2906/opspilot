"""Independent worker with renewable per-run leases and epoch-fenced writes."""

import asyncio
import signal
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from opspilot.config import Settings
from opspilot.contracts.api import CreateRun
from opspilot.db.models_workflow import AgentRun
from opspilot.runtime.fencing import Fence, execution_lease
from opspilot.runtime.jobs import claim, finish, reap
from opspilot.runtime.recovery import recover
from opspilot.runtime.run_service import RunService
from opspilot.telemetry import configure
from opspilot.tenancy.context import tenant_scope
from opspilot.tenancy.session import TenantSession


async def process_one(service: RunService, run_id: UUID | None = None) -> bool:
    await reap(service.engine, run_id)
    job = await claim(service.engine, run_id, service.settings.worker_lease_seconds)
    if job is None:
        return False
    async with execution_lease(
        service.engine,
        job["run_id"],
        service.settings,
        Fence(job["run_id"], job["claim_owner"], job["claim_epoch"]),
    ):
        try:
            async with TenantSession(service.engine) as session:
                run = await session.get(AgentRun, job["run_id"])
                if run is None:
                    raise RuntimeError("Command run missing")
            if run.workflow_version != "full-graph-v1":
                await service.fail(run.id, "UNSUPPORTED_WORKFLOW_VERSION")
            elif run.state_schema_version != 1:
                await service.fail(run.id, "CHECKPOINT_UNSUPPORTED")
            elif run.status == "queued" and job["kind"] == "start":
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
    try:
        while not stop.is_set():
            worked = False
            for tenant in settings.recovery_tenants:
                if stop.is_set():
                    break
                with tenant_scope(tenant):
                    try:
                        worked = await process_one(service) or worked
                    except (SQLAlchemyError, OSError):
                        # No claim is forgotten: unacknowledged work remains fenced for the reaper.
                        logger.warning("worker_database_unavailable")
                        try:
                            await asyncio.wait_for(stop.wait(), 0.5)
                        except TimeoutError:
                            pass
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), 0.25)
                except TimeoutError:
                    pass
    finally:
        # SIGTERM drains the active command before releasing ownership.
        await service.close()


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
