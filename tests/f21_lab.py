"""Real local HTTP/process/DB load lab; no vendor or model network calls.

Test sessions are explicitly inserted using the existing test-only session fixture.
This measures BFF session/auth/CSRF behavior, not IdP login scalability or HA.
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT
from tests.auth_helpers import session_client

TERMINAL = {"completed", "failed", "cancelled", "needs_attention"}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))], 3)


@dataclass
class Run:
    tenant: int
    request_id: UUID = field(default_factory=uuid4)
    run_id: str = ""
    action: dict = field(default_factory=dict)
    decision: str = "approve"
    final: dict = field(default_factory=dict)


class Lab:
    def __init__(self, seconds: int) -> None:
        self.settings = Settings()
        if self.settings.app_env != "test" or self.settings.llm_mode != "scripted":
            raise ValueError("Explicit scripted test profile required")
        if make_url(self.settings.database_url("migration")).database != "opspilot_full_test":
            raise ValueError("Isolated test database required")
        if self.settings.prometheus_registry_file:
            raise ValueError("External connector registrations forbidden in this lab")
        self.engine = create_engine(self.settings.database_url("migration"))
        self.seconds = seconds
        self.directory = Path(os.environ.get("F21_REPORT_DIR", "/reports"))
        self.directory.mkdir(exist_ok=True, parents=True)
        self.procs: list[asyncio.subprocess.Process] = []
        self.ports: list[int] = []
        self.worker_processes: list[asyncio.subprocess.Process] = []
        self.api_processes: list[asyncio.subprocess.Process] = []
        self.clients: list[list[httpx.AsyncClient]] = [[], []]
        self.latency: dict[str, list[float]] = {"create": [], "decision": [], "completion": []}
        self.counts: dict[str, int] = {}
        self.runs: list[Run] = []
        self.started = time.monotonic()
        self.report: dict = {
            "started_at": datetime.now(UTC).isoformat(),
            "scripted": True,
            "vendor_calls": 0,
            "paid_calls": 0,
            "idp_login_load_tested": False,
            "processes": {"api": 0, "worker": 0},
            "tenants": 2,
            "active_definition": (
                "accepted nonterminal runs, including queued and human approval wait"
            ),
            "simultaneous_worker_execution_claim": False,
            "requested_soak_seconds": seconds,
            "passed": False,
        }

    def save(self) -> None:
        self.report["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        self.report["http_status_counts"] = self.counts
        self.report["latency_seconds"] = {
            k: {
                "samples": len(v),
                "p50": percentile(v, 0.5),
                "p95": percentile(v, 0.95),
                "max": round(max(v), 3) if v else None,
            }
            for k, v in self.latency.items()
        }
        target = self.directory / "load-soak.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.replace(target)

    async def process(
        self,
        *args: str,
        worker: bool = False,
        legacy: bool = False,
        tenant_filter: str | None = None,
    ) -> asyncio.subprocess.Process:
        env = {**os.environ, "LLM_MODE": "scripted", "OPENAI_API_KEY": ""}
        if legacy:
            env.pop("PYTHONPATH", None)
        if tenant_filter:
            env["RECOVERY_TENANTS"] = json.dumps([tenant_filter])
        for key in (
            "MIGRATION_DATABASE_URL",
            "DOMAIN_DATABASE_URL",
            "PROMETHEUS_REGISTRY_FILE",
            "CONNECTOR_MANAGER_TOKEN_FILE",
        ):
            env.pop(key, None)
        if worker:
            env.pop("IDENTITY_DATABASE_URL", None)
            for key, name in (
                ("CA", "ca.crt"),
                ("CERT", "client.crt"),
                ("KEY", "client.key"),
                ("TOKEN", "token"),
            ):
                env["TELEMETRY_" + key + "_FILE"] = "/run/observability-worker/" + name
        else:
            for key in (
                "SECRET_MANAGER_URL",
                "SECRET_MANAGER_CA_FILE",
                "SECRET_MANAGER_TOKEN_FILE",
            ):
                env.pop(key, None)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            *args,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.procs.append(proc)
        (self.worker_processes if worker else self.api_processes).append(proc)
        return proc

    async def start(self, *, workers: bool = True) -> None:
        ports = []
        for _ in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        for port in ports:
            proc = await self.process(
                "-m",
                "uvicorn",
                "opspilot.api.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "error",
                "--no-access-log",
            )
            async with httpx.AsyncClient(timeout=3) as probe, asyncio.timeout(60):
                while True:
                    assert proc.returncode is None, "API process exited during setup"
                    try:
                        if (await probe.get(f"http://127.0.0.1:{port}/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.2)
            for tenant_index, tenant in enumerate((DEMO_TENANT, SECOND_TENANT)):
                client = httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{port}",
                    timeout=30,
                    limits=httpx.Limits(max_connections=100),
                )
                await session_client(client, self.settings, "demo", tenant)
                self.clients[tenant_index].append(client)
        self.ports = ports
        self.report["processes"]["api"] = 2
        self.report["api_pids"] = [proc.pid for proc in self.api_processes]
        if workers:
            await self.start_workers()
        self.report["platform"] = {
            "system": platform.system(),
            "machine": platform.machine(),
            "cpu_visible": os.cpu_count(),
        }
        self.report["phase"] = "burst"
        self.save()

    async def start_workers(self) -> None:
        for _ in range(2):
            await self.process("-m", "opspilot.runtime.worker", worker=True)
        self.report["processes"]["worker"] = 2
        self.report["worker_pids"] = [proc.pid for proc in self.worker_processes]

    async def request(
        self,
        tenant: int,
        index: int,
        method: str,
        path: str,
        body: dict | None = None,
        category: str | None = None,
    ) -> httpx.Response:
        started = time.monotonic()
        retry_count = 0
        # Only idempotent create/decision identities and reads may be replayed here.
        async with asyncio.timeout(180):
            while True:
                try:
                    response = await self.clients[tenant][index % 2].request(
                        method, path, json=body
                    )
                    status = str(response.status_code)
                    self.counts[status] = self.counts.get(status, 0) + 1
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        if category:
                            self.latency[category].append(time.monotonic() - started)
                        return response
                except httpx.TransportError:
                    self.counts["transport_error"] = self.counts.get("transport_error", 0) + 1
                retry_count += 1
                await asyncio.sleep(min(5, 0.25 * 2 ** min(retry_count, 5)))

    async def create(self, run: Run, index: int = 0) -> str:
        response = await self.request(
            run.tenant,
            index,
            "POST",
            "/api/v2/runs",
            {"request": "Investigate GreenShop", "client_request_id": str(run.request_id)},
            "create",
        )
        assert response.status_code == 202, f"Create returned {response.status_code}"
        return response.json()["run_id"]

    async def snapshot(self, run: Run) -> dict:
        response = await self.request(run.tenant, 0, "GET", "/api/v2/runs/" + run.run_id)
        assert response.status_code == 200, f"Snapshot returned {response.status_code}"
        return response.json()

    async def wait(self, run: Run, *, approval: bool = False) -> dict:
        async with asyncio.timeout(240):
            while True:
                snapshot = await self.snapshot(run)
                if snapshot["status"] in TERMINAL:
                    return snapshot
                if approval and snapshot["status"] == "waiting_for_approval":
                    return snapshot
                await asyncio.sleep(0.5)

    async def decide(self, run: Run, index: int = 0) -> int:
        response = await self.request(
            run.tenant,
            index,
            "POST",
            "/api/v2/runs/" + run.run_id + "/decision",
            {
                "action_id": run.action["action_id"],
                "expected_version": run.action["expected_version"],
                "decision": run.decision,
            },
            "decision",
        )
        assert response.status_code in {200, 202}, f"Decision returned {response.status_code}"
        return response.status_code

    async def burst(self) -> None:
        runs = [Run(i % 2, decision="approve" if i % 4 < 2 else "reject") for i in range(20)]
        tasks = [self.create(run, i) for run in runs for i in range(5)]
        ids = await asyncio.gather(*tasks)
        for index, run in enumerate(runs):
            group = ids[index * 5 : (index + 1) * 5]
            assert len(set(group)) == 1, "Duplicate create identity"
            run.run_id = group[0]
        self.runs.extend(runs)
        self.report["burst_creates_completed"] = len(ids)
        self.save()
        snapshots = await asyncio.gather(*(self.wait(run, approval=True) for run in runs))
        for run, snapshot in zip(runs, snapshots, strict=True):
            assert snapshot["status"] == "waiting_for_approval", (
                "Happy-path burst did not reach approval"
            )
            run.action = snapshot["action"]
        self.report["burst"] = {
            "concurrent_create_requests": 100,
            "distinct_runs": 20,
            "observed_nonterminal_runs": len(snapshots),
            "concurrent_decision_requests": 100,
        }
        self.save()
        # Foreign tenant must not see a single byte of the owned run's snapshot.
        for run in runs:
            response = await self.request(1 - run.tenant, 1, "GET", "/api/v2/runs/" + run.run_id)
            assert response.status_code == 404, "Cross-tenant disclosure"
        await asyncio.gather(*(self.decide(run, i) for run in runs for i in range(5)))
        self.report["burst_decisions_completed"] = 100
        self.save()
        for run in runs:
            run.final = await self.wait(run)
            assert run.final["status"] == "completed", "Happy-path burst not completed"
            assert run.final["outcome"] == (
                "actions_verified" if run.decision == "approve" else "rejected"
            )
        self.report["burst"]["completed"] = len(runs)
        self.report["burst"]["cross_tenant_denials"] = len(runs)
        self.save()

    async def cycle(self, run: Run) -> None:
        started = time.monotonic()
        run.run_id = await self.create(run)
        self.runs.append(run)
        snapshot = await self.wait(run, approval=True)
        if snapshot["status"] == "waiting_for_approval":
            run.action = snapshot["action"]
            await self.decide(run)
            run.final = await self.wait(run)
        else:
            run.final = snapshot
        self.latency["completion"].append(time.monotonic() - started)

    async def quota_burst(self) -> None:
        """100 distinct identities also exercise bounded admission, not just replay."""
        attempts = [Run(i % 2, decision="reject") for i in range(100)]
        self.report["phase"] = "quota_burst"
        self.save()
        responses = await asyncio.gather(
            *(
                self.clients[run.tenant][(index // 2) % 2].post(
                    "/api/v2/runs",
                    json={
                        "request": "Investigate GreenShop",
                        "client_request_id": str(run.request_id),
                    },
                )
                for index, run in enumerate(attempts)
            )
        )
        statuses: dict[str, int] = {}
        denials: dict[str, int] = {}
        accepted = []
        for run, response in zip(attempts, responses, strict=True):
            code = str(response.status_code)
            statuses[code] = statuses.get(code, 0) + 1
            if response.status_code == 202:
                run.run_id = response.json()["run_id"]
                accepted.append(run)
            elif response.status_code == 429:
                reason = response.json().get("error", {}).get("code", "unknown")
                denials[reason] = denials.get(reason, 0) + 1
        self.report["quota_burst"] = {
            "concurrent_distinct_create_requests": 100,
            "http_status_counts": statuses,
            "denial_codes": denials,
            "accepted": len(accepted),
            "actor_active_limit": 32,
            "tenant_active_limit": 40,
            "global_active_limit": 64,
        }
        self.save()
        assert all(r.status_code in {202, 429} for r in responses), (
            "Unexpected quota burst response"
        )
        assert 0 < len(accepted) <= 32 and denials.get("RUN_ADMISSION_LIMIT", 0), (
            "Admission bound not exercised"
        )
        self.runs.extend(accepted)
        for run in accepted:
            snapshot = await self.wait(run, approval=True)
            assert snapshot["status"] == "waiting_for_approval"
            run.action = snapshot["action"]
        await asyncio.gather(*(self.decide(run, i) for i, run in enumerate(accepted)))
        for run in accepted:
            run.final = await self.wait(run)
            assert run.final["outcome"] == "rejected"
        self.report["quota_burst"]["terminal_rejected"] = len(accepted)
        self.save()

    async def soak(self) -> None:
        start = time.monotonic()
        self.report["phase"] = "soak"
        # 100 runs -> at least200 start/resume jobs, spread across the measured window.
        self.report["soak"] = {"planned_runs": 100, "completed_runs": 0, "measured_seconds": 0}
        paused = Run(0, decision="reject")
        paused.run_id = await self.create(paused)
        self.runs.append(paused)
        paused_snapshot = await self.wait(paused, approval=True)
        assert paused_snapshot["status"] == "waiting_for_approval"
        paused_since = time.monotonic()
        self.save()
        for batch in range(50):
            due = start + batch * self.seconds / 50
            await asyncio.sleep(max(0, due - time.monotonic()))
            tasks = [asyncio.create_task(self.cycle(Run(tenant))) for tenant in (0, 1)]
            if batch in {5, 10}:
                await asyncio.sleep(0.25)
                started_fault = time.monotonic()
                if batch == 5:
                    target = self.worker_processes[0]
                    if target.returncode is None:
                        target.kill()
                        await target.wait()
                    await self.process("-m", "opspilot.runtime.worker", worker=True)
                    kind = "worker_sigkill"
                else:
                    target = self.api_processes[0]
                    if target.returncode is None:
                        target.kill()
                        await target.wait()
                    port = self.ports[0]
                    replacement = await self.process(
                        "-m",
                        "uvicorn",
                        "opspilot.api.main:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "error",
                        "--no-access-log",
                    )
                    async with httpx.AsyncClient(timeout=2) as probe, asyncio.timeout(60):
                        while True:
                            assert replacement.returncode is None
                            try:
                                response = await probe.get(f"http://127.0.0.1:{port}/health")
                                if response.status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                            await asyncio.sleep(0.2)
                    kind = "api_sigkill"
                self.report.setdefault("process_faults", []).append(
                    {
                        "kind": kind,
                        "batch": batch + 1,
                        "replacement_seconds": round(time.monotonic() - started_fault, 3),
                    }
                )
            await asyncio.gather(*tasks)
            self.report["soak"]["completed_runs"] += 2
            self.report["soak"]["measured_seconds"] = round(time.monotonic() - start, 3)
            self.save()
            print(
                json.dumps(
                    {
                        "phase": "soak",
                        "batch": batch + 1,
                        "completed_runs": self.report["soak"]["completed_runs"],
                    }
                ),
                flush=True,
            )
        await asyncio.sleep(max(0, start + self.seconds - time.monotonic()))
        self.report["soak"]["measured_seconds"] = round(time.monotonic() - start, 3)
        paused.final = await self.wait(paused)
        self.report["long_human_pause"] = {
            "measured_seconds": round(time.monotonic() - paused_since, 3),
            "status": paused.final["status"],
            "outcome": paused.final.get("outcome"),
            "new_approval_not_assumed": True,
        }

    async def invariants(self, minimum_jobs: int = 240) -> None:
        ids = [UUID(run.run_id) for run in self.runs]
        async with self.engine.connect() as conn:
            jobs = list(
                (
                    await conn.execute(
                        text(
                            "SELECT status,count(*) FROM workflow.command_jobs WHERE "
                            "run_id=ANY(:ids) GROUP BY status"
                        ),
                        {"ids": ids},
                    )
                ).all()
            )
            duplicates = await conn.scalar(
                text(
                    "SELECT count(*) FROM (SELECT originating_action_id FROM "
                    "domain.tickets WHERE originating_action_id IN (SELECT id FROM "
                    "workflow.actions WHERE run_id=ANY(:ids)) GROUP BY "
                    "originating_action_id HAVING count(*)>1) x"
                ),
                {"ids": ids},
            )
            unauthorized = await conn.scalar(
                text(
                    "SELECT count(*) FROM domain.tickets t JOIN workflow.actions a ON "
                    "a.id=t.originating_action_id AND a.tenant_id=t.tenant_id LEFT "
                    "JOIN workflow.approvals p ON p.action_id=a.id AND "
                    "p.tenant_id=a.tenant_id WHERE a.run_id=ANY(:ids) AND (p.decision "
                    "IS DISTINCT FROM 'approved' OR "
                    "a.arguments->>'customer_id'<>t.customer_id::text)"
                ),
                {"ids": ids},
            )
            states = list(
                (
                    await conn.execute(
                        text(
                            "SELECT status,count(*) FROM workflow.agent_runs WHERE "
                            "id=ANY(:ids) GROUP BY status"
                        ),
                        {"ids": ids},
                    )
                ).all()
            )
            needs_reason = await conn.scalar(
                text(
                    "SELECT count(*) FROM workflow.agent_runs WHERE id=ANY(:ids) AND "
                    "status='needs_attention' AND (error IS NULL OR error->>'code' IS "
                    "NULL)"
                ),
                {"ids": ids},
            )
            failed_verification = 0
            rejected_writes = 0
            for run in self.runs:
                tickets = await conn.scalar(
                    text(
                        "SELECT count(*) FROM domain.tickets WHERE "
                        "originating_action_id IN (SELECT id FROM workflow.actions "
                        "WHERE run_id=:id)"
                    ),
                    {"id": UUID(run.run_id)},
                )
                if run.decision == "reject":
                    rejected_writes += tickets
                if run.final.get("outcome") == "actions_verified" and tickets != 1:
                    failed_verification += 1
        assert (
            not duplicates
            and not unauthorized
            and not rejected_writes
            and not failed_verification
            and not needs_reason
        ), "Safety invariant violated"
        assert all(state in TERMINAL for state, _ in states), "Accepted run still nonterminal"
        assert all(state in {"done", "dead"} for state, _ in jobs), "Accepted job still nonterminal"
        self.report["invariants"] = {
            "duplicate_local_writes": duplicates,
            "unauthorized_local_writes": unauthorized,
            "rejected_action_writes": rejected_writes,
            "false_verified_successes": failed_verification,
            "needs_attention_without_reason": needs_reason,
        }
        self.report["terminal_runs"] = dict(states)
        self.report["terminal_jobs"] = dict(jobs)
        self.report["run_count"] = len(ids)
        self.report["job_count"] = sum(count for _, count in jobs)
        assert self.report["job_count"] >= minimum_jobs, "Insufficient jobs for burst plus soak"

    async def close(self) -> None:
        for proc in self.procs:
            if proc.returncode is None:
                proc.terminate()
        for proc in self.procs:
            try:
                await asyncio.wait_for(proc.wait(), 20)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        for group in self.clients:
            for client in group:
                await client.aclose()
        await self.engine.dispose()

    async def run(self, *, smoke: bool = False) -> int:
        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(10)
                self.report["process_health"] = {
                    "api_alive": sum(p.returncode is None for p in self.api_processes),
                    "worker_alive": sum(p.returncode is None for p in self.worker_processes),
                }
                self.save()

        pulse = asyncio.create_task(heartbeat())
        try:
            await self.start()
            await self.burst()
            if not smoke:
                await self.quota_burst()
                await self.soak()
            await self.invariants(40 if smoke else 240)
            self.report["passed"] = not smoke and self.seconds >= 1800
            self.report["smoke_only"] = smoke
            self.report["phase"] = "finished"
            return 0 if self.report["passed"] else 2
        except Exception as exc:
            # No raw HTTP/provider exceptions, bodies, headers or credentials in reports.
            self.report["error_class"] = type(exc).__name__
            if isinstance(exc, AssertionError):
                self.report["assertion"] = str(exc)
            self.report["phase"] = "failed"
            return 1
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
            self.save()
            await self.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soak-seconds", type=int, default=1800)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.soak_seconds <= 7200:
        parser.error("Soak duration must be between1 and7200 seconds")
    raise SystemExit(asyncio.run(Lab(args.soak_seconds).run(smoke=args.smoke)))
