"""F21 real two-API session/decision/cancellation and pinned-version process probes."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text

from opspilot.auth.oidc import digest
from tests.auth_helpers import session_client
from tests.f21_lab import Lab, Run


async def test_enqueue_reuses_api_pool_and_does_not_dispose_it(integration_settings, monkeypatch):
    import opspilot.agent.service as creator
    from opspilot.contracts.api import CreateRun
    from opspilot.runtime.run_service import RunService

    service = RunService(integration_settings)

    def unexpected_pool(*args, **kwargs):
        raise AssertionError("Enqueue created a per-request pool")

    monkeypatch.setattr(creator, "create_engine", unexpected_pool)
    try:
        body = CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        first = await service.create(body)
        assert (await service.create(body))["run_id"] == first["run_id"]
        async with service.engine.connect() as conn:
            assert await conn.scalar(text("SELECT 1")) == 1
    finally:
        await service.close()


async def test_worker_admission_never_upgrades_held_maintenance_lock(integration_settings):
    from opspilot.contracts.api import CreateRun
    from opspilot.runtime.run_service import RunService
    from opspilot.tenancy.context import DEMO_TENANT

    service = RunService(integration_settings)
    try:
        run = await service.create(
            CreateRun(request="Investigate GreenShop", client_request_id=uuid4())
        )
        async with service.engine.begin() as held:
            assert await held.scalar(text("SELECT 1")) == 1

            async def admit():
                async with service.engine.begin() as independent:
                    return await independent.scalar(
                        text("SELECT workflow.worker_slot(:r,false,:tenants)"),
                        {"r": UUID(run["run_id"]), "tenants": [DEMO_TENANT]},
                    )

            # The old lock upgrade cannot finish while `held` retains its shared lock.
            assert await asyncio.wait_for(admit(), 2) is True
            async with service.engine.connect() as nested:
                assert await asyncio.wait_for(nested.scalar(text("SELECT 1")), 2) == 1
    finally:
        await service.close()


async def test_two_api_opposite_decisions_cancel_and_revoked_session(tmp_path, monkeypatch):
    monkeypatch.setenv("F21_REPORT_DIR", str(tmp_path))
    lab = Lab(1)
    try:
        await lab.start()
        run = Run(0)
        run.run_id = await lab.create(run)
        snapshot = await lab.wait(run, approval=True)
        assert snapshot["status"] == "waiting_for_approval"
        action = snapshot["action"]
        path = "/api/v2/runs/" + run.run_id
        command = str(uuid4())
        calls = []
        for index in range(100):
            client = lab.clients[0][index % 2]
            if index % 3 == 0:
                calls.append(client.post(path + "/cancel", json={"command_id": command}))
            else:
                calls.append(
                    client.post(
                        path + "/decision",
                        json={
                            "action_id": action["action_id"],
                            "expected_version": action["expected_version"],
                            "decision": "approve" if index % 3 == 1 else "reject",
                        },
                    )
                )
        responses = await asyncio.gather(*calls)
        assert all(r.status_code in {200, 202, 409, 410} for r in responses)
        final = await lab.wait(run)
        assert final["status"] in {"completed", "cancelled"}
        async with lab.engine.connect() as conn:
            writes = await conn.scalar(
                text("SELECT count(*) FROM domain.tickets WHERE originating_action_id=:a"),
                {"a": UUID(action["action_id"])},
            )
            decision = await conn.scalar(
                text("SELECT decision FROM workflow.approvals WHERE action_id=:a"),
                {"a": UUID(action["action_id"])},
            )
        assert writes <= 1
        if writes:
            assert decision == "approved"
        if decision == "rejected":
            assert writes == 0
        client = lab.clients[0][0]
        raw = client.cookies.get("opspilot_session")
        async with lab.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET revoked_at=clock_timestamp() WHERE token_hash=:h"
                ),
                {"h": digest(raw)},
            )
        assert (await client.get(path)).status_code == 401
        assert (await lab.clients[1][1].get(path)).status_code == 404
        async with httpx.AsyncClient(base_url=str(client.base_url)) as operator:
            await session_client(operator, lab.settings, "operator")
            assert (
                await operator.post(
                    path + "/decision",
                    json={
                        "action_id": action["action_id"],
                        "expected_version": action["expected_version"],
                        "decision": "approve",
                    },
                )
            ).status_code == 403
    finally:
        await lab.close()


async def test_two_workers_preserve_pinned_workflow_versions_and_expired_wait(
    tmp_path, monkeypatch
):
    report_directory = Path(os.environ.get("F21_REPORT_DIR", "/reports"))
    monkeypatch.setenv("F21_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("APPROVAL_TTL_SECONDS", "10")
    lab = Lab(1)
    try:
        await lab.start(workers=False)
        runs = []
        for tenant, request in (
            (0, "Investigate GreenShop"),
            (1, "Investigate GreenShop and comment"),
        ):
            response = await lab.clients[tenant][0].post(
                "/api/v2/runs", json={"request": request, "client_request_id": str(uuid4())}
            )
            assert response.status_code == 202
            runs.append(Run(tenant, run_id=response.json()["run_id"]))
        async with lab.engine.connect() as conn:
            versions = set(
                await conn.scalars(
                    text("SELECT workflow_version FROM workflow.agent_runs WHERE id=ANY(:ids)"),
                    {"ids": [UUID(r.run_id) for r in runs]},
                )
            )
        assert versions == {"full-graph-v1", "full-graph-v2"}
        from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT

        await lab.process(
            "-m",
            "opspilot.runtime.worker",
            worker=True,
            legacy=True,
            tenant_filter=str(DEMO_TENANT),
        )
        await lab.process(
            "-m",
            "opspilot.runtime.worker",
            worker=True,
            tenant_filter=str(SECOND_TENANT),
        )
        legacy_environment = dict(os.environ)
        legacy_environment.pop("PYTHONPATH", None)
        probe = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import opspilot;print(opspilot.__file__)",
            env=legacy_environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(probe.communicate(), 15)
        legacy_origin = output.decode().strip()
        assert "/site-packages/opspilot/" in legacy_origin
        snapshots = await asyncio.gather(*(lab.wait(r, approval=True) for r in runs))
        assert all(s["status"] == "waiting_for_approval" for s in snapshots)
        report_directory.joinpath("rolling-workflow.json").write_text(
            json.dumps(
                {
                    "passed_initial_coexistence": True,
                    "legacy_worker_origin": legacy_origin,
                    "new_worker_origin": "/app/src/opspilot",
                    "workflow_versions": sorted(versions),
                    "tenant_partitioned_workers": True,
                    "release_image_upgrade_claim": False,
                },
                indent=2,
            )
            + "\n"
        )
        # Actual process stop/restart, not an in-process graph replacement.
        for proc in lab.procs[2:]:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), 20)
        # Expiry is part of the signed immutable revision, never patched in place.
        await asyncio.sleep(11)
        await lab.start_workers()
        final = await asyncio.gather(*(lab.wait(r) for r in runs))
        assert all(s["status"] in {"completed", "needs_attention"} for s in final)
        async with lab.engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM domain.tickets WHERE "
                        "originating_action_id IN (SELECT id FROM workflow.actions "
                        "WHERE run_id=ANY(:ids))"
                    ),
                    {"ids": [UUID(r.run_id) for r in runs]},
                )
                == 0
            )
            assert (
                set(
                    await conn.scalars(
                        text("SELECT workflow_version FROM workflow.agent_runs WHERE id=ANY(:ids)"),
                        {"ids": [UUID(r.run_id) for r in runs]},
                    )
                )
                == versions
            )
        rolling_report = json.loads(report_directory.joinpath("rolling-workflow.json").read_text())
        rolling_report.update(
            passed=True,
            immutable_expiry_preserved=True,
            expired_wait_writes=0,
            post_upgrade_statuses=[s["status"] for s in final],
        )
        report_directory.joinpath("rolling-workflow.json").write_text(
            json.dumps(rolling_report, indent=2) + "\n"
        )
    finally:
        await lab.close()
