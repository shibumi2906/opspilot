import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.contracts.api import CreateRun, Decision
from opspilot.runtime.run_service import RunService

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_F06_PROCESSES") != "1", reason="Dedicated real multiworker gate"
)


@pytest.mark.parametrize("fault", ["kill", "stop", "partition"])
async def test_two_workers_expiry_and_stale_boundaries(
    integration_settings, admin_engine, tmp_path, fault
):
    service = RunService(integration_settings)
    result = await service.create(
        CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
    )
    run = UUID(result["run_id"])
    release = tmp_path / "release"
    blocked = False
    sockets = set()
    processes = []
    db = make_url(integration_settings.database_url("workflow"))

    async def proxy(reader, writer):
        sockets.add(writer)
        upstream = None
        try:
            if blocked:
                return
            other, upstream = await asyncio.open_connection(db.host, db.port or 5432)
            sockets.add(upstream)

            async def copy(source, dest):
                while chunk := await source.read(65536):
                    if blocked:
                        break
                    dest.write(chunk)
                    await dest.drain()

            tasks = [
                asyncio.create_task(copy(reader, upstream)),
                asyncio.create_task(copy(other, writer)),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            sockets.discard(writer)
            if upstream:
                upstream.close()
                sockets.discard(upstream)

    server = await asyncio.start_server(proxy, "127.0.0.1", 0)
    proxy_port = server.sockets[0].getsockname()[1]

    async def start():
        env = {
            **os.environ,
            "F06_RUN": str(run),
            "F06_RELEASE": str(release),
            "F06_HOLD_SDK": "1" if fault == "stop" else "0",
        }
        if fault == "partition":
            for role in ("workflow", "checkpoint"):
                url = make_url(integration_settings.database_url(role)).set(
                    host="127.0.0.1", port=proxy_port
                )
                env[role.upper() + "_DATABASE_URL"] = url.render_as_string(hide_password=False)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.f06_fault_worker",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes.append(proc)
        return proc

    async def wait_status(expected):
        async with asyncio.timeout(45):
            while True:
                current = await service.snapshot(run)
                if current["status"] in expected:
                    return current
                await asyncio.sleep(0.05)

    try:
        # Both real processes contend for the same run. Exactly one receives epoch 1.
        first, second = await asyncio.gather(start(), start())
        reads = [asyncio.create_task(proc.stdout.readline()) for proc in processes]
        done, pending = await asyncio.wait(reads, timeout=20, return_when=asyncio.FIRST_COMPLETED)
        assert len(done) == 1
        winner = reads.index(next(iter(done)))
        claim = json.loads(next(iter(done)).result())
        assert claim["epoch"] == 1
        assert claim["held_sdk_transaction"] == (fault == "stop")
        old = processes[winner]
        survivor = processes[1 - winner]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if fault == "kill":
            old.kill()
            await old.wait()
        elif fault == "stop":
            old.send_signal(signal.SIGSTOP)
        else:
            # The old worker goes through a real TCP proxy; isolate only that process.
            # Route the survivor directly before partitioning the winner's existing connections.
            survivor.terminate()
            await survivor.wait()
            blocked = True
            for writer in list(sockets):
                writer.close()
            survivor = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "opspilot.runtime.worker",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            processes.append(survivor)
        pending = await wait_status({"waiting_for_approval", "failed", "needs_attention"})
        assert pending["status"] == "waiting_for_approval", pending
        await service.decide(
            run,
            Decision(
                expected_version=1, action_id=pending["action"]["action_id"], decision="approve"
            ),
        )
        final = await wait_status({"completed", "failed", "needs_attention"})
        assert final["outcome"] == "actions_verified", final
        if fault != "kill":
            blocked = False
            await asyncio.to_thread(release.write_text, "release")
            if fault == "stop":
                old.send_signal(signal.SIGCONT)
            line = await asyncio.wait_for(old.stdout.readline(), 20)
            late = json.loads(line)
            assert set(late["late_rejected"]) == {
                "projection",
                "action",
                "approval",
                "checkpoint",
                "pending_writes",
                "operation",
                "read_dispatch",
                "model_dispatch",
            }, late
            assert await asyncio.wait_for(old.wait(), 15) != 0
        async with asyncio.timeout(10):
            while True:
                async with admin_engine.connect() as conn:
                    outstanding = await conn.scalar(
                        text(
                            "SELECT count(*) FROM workflow.command_jobs "
                            "WHERE run_id=:r AND status<>'done'"
                        ),
                        {"r": run},
                    )
                if outstanding == 0:
                    break
                await asyncio.sleep(0.02)
        stable = await service.snapshot(run)
        assert stable["report"] == final["report"] and "stale" not in stable
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                    {"a": UUID(final["action"]["action_id"])},
                )
                == 1
            )
            row = (
                await conn.execute(
                    text("SELECT epoch,owner FROM workflow.run_execution_leases WHERE run_id=:r"),
                    {"r": run},
                )
            ).one()
            assert row.epoch >= 3 and row.owner is None
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM checkpoints.checkpoint_writes WHERE thread_id=:r "
                        "AND channel='late'"
                    ),
                    {"r": str(run)},
                )
                == 0
            )
        async with admin_engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM checkpoints.checkpoint_blobs "
                        "WHERE thread_id=:r AND channel='late'"
                    ),
                    {"r": str(run)},
                )
                == 0
            )
        report = {
            "fault": fault,
            "run": str(run),
            "old_epoch": 1,
            "final_epoch": row.epoch,
            "outcome": final["outcome"],
            "tickets": 1,
            "stale_boundaries": 8 if fault != "kill" else 0,
            "held_sdk_transaction": fault == "stop",
        }
        report_dir = os.environ.get("F06_REPORT_DIR")
        if report_dir:
            await asyncio.to_thread(
                Path(report_dir, f"{fault}.json").write_text, json.dumps(report, indent=2) + "\n"
            )
    finally:
        blocked = False
        await asyncio.to_thread(release.touch)
        for proc in processes:
            if proc.returncode is None:
                proc.send_signal(signal.SIGCONT)
                proc.kill()
                await proc.wait()
        for writer in list(sockets):
            writer.close()
        server.close()
        await server.wait_closed()
        await service.close()
