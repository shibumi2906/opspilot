"""Scripted Full eval harness: BFF roles, durable jobs, real MCP transport and DB.

ASGI HTTP transport exercises middleware/routes; worker claim/execute/finish runs
in this process. This is not process-isolation, IdP login or live Jira evidence.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from contextlib import AsyncExitStack, nullcontext
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.prompts import SYSTEM_PROMPT
from opspilot.api.main import create_app
from opspilot.auth.execution import execution_scope
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.evals.assertions import evaluate
from opspilot.evals.full import accounting, schedule
from opspilot.evals.runner import articles, count_tickets, database_checks, source
from opspilot.evals.token_guard import TokenGuard
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import process_one
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT, tenant_scope
from tests.auth_helpers import session_client


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def continuation(previous, planned, settings):
    report = json.loads(previous.read_text(encoding="utf-8"))
    cases = report["cases"]
    expected = [(case.id, repeat) for case, repeat in planned]
    if (
        report["mode"] != "real"
        or report["requested_model"] != settings.openai_model
        or report["fixed_config"]["reasoning_effort"] != settings.openai_reasoning_effort
        or report["prompt_sha256"] != hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
        or report["token_guard"]["stop_reason"] != "GLOBAL_TOKEN_LIMIT"
        or report["token_guard"]["unknown_usage"] != 0
        or not 0 < len(cases) < len(planned)
        or [(case["id"], case["repeat"]) for case in cases] != expected[: len(cases)]
        or [(row["id"], row["repeat"]) for row in report["remaining_schedule"]]
        != expected[len(cases) :]
    ):
        raise ValueError("Prior report is not a compatible quota-stopped schedule prefix")
    return report


async def run_case(settings, item, engine):
    case, repeat = item
    spec = case.scenario
    tenant = (DEMO_TENANT, SECOND_TENANT)[case.tenant]
    result = dict(
        id=case.id,
        repeat=repeat,
        split=case.split,
        category=case.category,
        asvs_ids=case.asvs_ids,
        passed=False,
        setup_error=None,
        errors=[],
        usage=None,
        snapshot=None,
        db=None,
        model_spend_usd=0 if settings.llm_mode == "scripted" else None,
    )
    run_id = None
    before = await count_tickets(engine)
    before_decision = before
    try:
        configured = settings.model_copy(
            update={
                "scenario_id": spec.fixture,
                "scenario_clock": spec.clock,
                "agent_max_reads": spec.limits.reads,
                "agent_max_llm_attempts": spec.limits.llm_attempts,
                "agent_max_rounds": spec.limits.rounds,
                "agent_max_tokens": spec.limits.tokens,
                "agent_active_seconds": spec.limits.active_seconds,
            }
        )
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(articles(engine, spec.article_overlay))
            configured = await stack.enter_async_context(source(configured))
            app = create_app(configured)
            await stack.enter_async_context(app.router.lifespan_context(app))
            clients = {}
            for name, who, selected in (
                ("owner", "operator", tenant),
                ("approver", "approver", tenant),
                ("foreign", "demo", (SECOND_TENANT, DEMO_TENANT)[case.tenant]),
                ("anonymous", None, tenant),
            ):
                client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url=configured.app_origin
                    )
                )
                if who:
                    await session_client(client, configured, who, selected)
                clients[name] = client
            response = await clients["owner"].post(
                "/api/v2/runs", json={"request": spec.request, "client_request_id": str(uuid4())}
            )
            assert response.status_code == 202, "CREATE_HTTP_" + str(response.status_code)
            run_id = UUID(response.json()["run_id"])
            path = "/api/v2/runs/" + str(run_id)
            service = RunService(configured)
            stack.push_async_callback(service.close)

            async def advance():
                with tenant_scope(tenant):
                    assert await process_one(service, run_id), "JOB_NOT_CLAIMED"
                response = await clients["owner"].get(path)
                assert response.status_code == 200, "SNAPSHOT_HTTP_" + str(response.status_code)
                return response.json()

            snapshot = await advance()
            result["snapshot"] = snapshot
            before_decision = await count_tickets(engine)
            if case.probe in {"cross_tenant", "anonymous"}:
                who, status = (
                    ("foreign", 404) if case.probe == "cross_tenant" else ("anonymous", 401)
                )
                assert (await clients[who].get(path)).status_code == status, "ACCESS_PROBE"
            action = None
            for choice in spec.human_decisions:
                # A repeated decision uses the original immutable action/version.
                if snapshot.get("action"):
                    action = snapshot["action"]
                if action is None:
                    result["errors"].append("EXPECTED_ACTION_MISSING")
                    break
                body = dict(
                    action_id=action["action_id"],
                    expected_version=action["expected_version"],
                    decision=choice,
                )
                if case.probe == "operator_denied":
                    assert (
                        await clients["owner"].post(path + "/decision", json=body)
                    ).status_code == 403
                if case.probe == "csrf":
                    client = clients["approver"]
                    csrf = client.headers.pop("X-CSRF-Token")
                    try:
                        assert (await client.post(path + "/decision", json=body)).status_code == 403
                    finally:
                        client.headers["X-CSRF-Token"] = csrf
                response = await clients["approver"].post(path + "/decision", json=body)
                assert response.status_code in {200, 202}, "DECISION_HTTP_" + str(
                    response.status_code
                )
                if snapshot["status"] != "completed":
                    snapshot = await advance()
            result["snapshot"] = snapshot
            with tenant_scope(tenant):
                async with (
                    execution_scope(service.engine, run_id),
                    postgres_checkpointer(configured) as saver,
                ):
                    saved = await saver.aget_tuple({"configurable": {"thread_id": str(run_id)}})
                assert saved is not None, "CHECKPOINT_MISSING"
                state = dict(saved.checkpoint["channel_values"])
            db = await database_checks(engine, run_id, before, before_decision)
            async with engine.connect() as conn:
                jobs = [
                    dict(r)
                    for r in (
                        await conn.execute(
                            text(
                                "SELECT kind,status,attempts FROM workflow.command_jobs "
                                "WHERE run_id=:r"
                            ),
                            {"r": run_id},
                        )
                    ).mappings()
                ]
                actions = [
                    dict(r)
                    for r in (
                        await conn.execute(
                            text(
                                "SELECT x.tool_name,a.decision,x.execution_status "
                                "FROM workflow.actions x LEFT JOIN workflow.approvals a "
                                "ON a.action_id=x.id WHERE x.run_id=:r"
                            ),
                            {"r": run_id},
                        )
                    ).mappings()
                ]
            metrics = evaluate(spec, state, db)
            result.update(
                db=db,
                jobs=jobs,
                per_action=actions,
                usage=state.get("budget"),
                selection=metrics["tools"],
                metrics=metrics,
                report=state.get("final_report"),
                verification_calls=[
                    c for c in state.get("tool_calls", {}).values() if c.get("verification")
                ],
                evidence=state.get("evidence"),
                run_id=str(run_id),
            )
            result["errors"].extend(metrics["errors"])
            if not jobs or any(j["status"] != "done" for j in jobs):
                result["errors"].append("DURABLE_JOBS_NOT_DONE")
            if any(
                not e.get("source_type") or not e.get("source_id")
                for e in snapshot.get("evidence", [])
            ):
                result["errors"].append("SOURCE_LABEL_MISSING")
            if snapshot["status"] != spec.expected_status:
                result["errors"].append("PUBLIC_STATUS")
            result["passed"] = not result["errors"]
    except Exception as exc:
        # Never persist provider bodies, headers, credentials, connection strings.
        result["setup_error"] = type(exc).__name__ if run_id is None else None
        result["errors"].append("EXECUTION_" + type(exc).__name__)
        if isinstance(exc, AssertionError):
            result["assertion"] = str(exc)[:100]
    return result


async def main(args):
    if args.mode == "real" and not args.authorize_real:
        raise ValueError("Real execution requires explicit separate owner authorization")
    settings = Settings(llm_mode=args.mode)
    if settings.app_env != "test":
        raise ValueError("Only isolated test execution allowed")
    if args.mode == "real" and (not settings.openai_api_key or not settings.openai_model):
        raise ValueError("Real execution requires local credentials and fixed model")
    if args.mode == "real" and not args.free_quota_confirmed:
        raise ValueError("Confirm account/project/model free quota before any real dispatch")
    for role in ("migration", "workflow", "domain", "checkpoint", "identity"):
        if make_url(settings.database_url(role)).database != "opspilot_full_test":
            raise ValueError("Isolated Full test DSNs required")
    if settings.prometheus_registry_file:
        raise ValueError("No external connectors allowed")
    output = Path(os.environ.get("F22_REPORT_DIR", "/reports"))
    planned = schedule(args.mode)
    previous = os.environ.get("F22_PREVIOUS_REPORT")
    prior = (
        continuation(Path(previous), planned, settings)
        if previous and args.mode == "real"
        else None
    )
    prior_cases = prior["cases"] if prior else []
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    token_guard = (
        TokenGuard(output / "token-ledger.json", args.total_token_limit, settings.openai_model)
        if args.mode == "real"
        else None
    )
    engine = create_engine(settings.database_url("migration"))
    report = dict(
        stage="F22",
        mode=args.mode,
        timestamp=datetime.now(UTC).isoformat(),
        commit=os.environ["F22_COMMIT"],
        dirty_snapshot=True,
        prompt_sha256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        dependencies={n: version(n) for n in ("langgraph", "mcp", "psycopg", "httpx")},
        cases=[],
        provenance={},
        paid_calls=0 if args.mode == "scripted" else None,
        requested_model=settings.openai_model if args.mode == "real" else None,
        vendor_calls=0,
        transport="ASGI BFF HTTP + native MCP TCP; in-process durable worker",
        human_claim_review="pending",
        holdout_unseen=False,
        harness_sha256=await asyncio.to_thread(file_hash, __file__),
        lock_sha256=await asyncio.to_thread(file_hash, "/app/uv.lock"),
        fixture_session_auth=True,
        real_idp_login=False,
        source_label="synthetic local fixture; no live connector acceptance",
        fixed_config={
            "security_profile": settings.security_profile,
            "recovery_tenants": [str(t) for t in settings.recovery_tenants],
            "corpus": "full-split.json",
            "reasoning_effort": settings.openai_reasoning_effort,
        },
        remaining_schedule=[],
        previous_report=previous if prior else None,
        previous_report_sha256=file_hash(previous) if prior else None,
        previous_recorded_runs=len(prior_cases),
    )

    def save():
        report["summary"] = accounting(prior_cases + report["cases"], args.mode)
        if token_guard:
            report["token_guard"] = token_guard.snapshot()
            report["free_quota_confirmation"] = "operator attestation; not a billing API proof"
        (output / (args.mode + ".json")).write_text(
            json.dumps(report, indent=2, default=str) + "\n"
        )

    try:
        async with engine.connect() as guard:
            assert await guard.scalar(text("SELECT current_database()")) == "opspilot_full_test"
            assert await guard.scalar(text("SELECT pg_try_advisory_lock(1801202622)"))
            for position, item in enumerate(planned[len(prior_cases) :], start=len(prior_cases)):
                if token_guard and token_guard.stop_reason:
                    report["remaining_schedule"] = [
                        dict(id=c.id, repeat=n, reason=token_guard.stop_reason)
                        for c, n in planned[position:]
                    ]
                    break
                with token_guard.installed() if token_guard else nullcontext():
                    result = await run_case(settings, item, engine)
                report["cases"].append(result)
                save()
                print(result["id"], result["passed"], result["errors"], flush=True)
                if len(report["cases"]) == int(os.environ.get("F22_DIAGNOSTIC_LIMIT", "0")):
                    break
            # Exact imported source/fixture/config hashes, no runtime secrets.
            paths = {
                Path(m.__file__)
                for n, m in sys.modules.items()
                if n.startswith("opspilot") and getattr(m, "__file__", None)
            }

            def fixture_paths():
                return list(Path("/app/src/opspilot/fixtures").glob("*.json")) + list(
                    Path("/app/src/opspilot/evals").glob("*.json")
                )

            paths.update(await asyncio.to_thread(fixture_paths))
            for path in sorted(paths):
                report["provenance"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            save()
    finally:
        await engine.dispose()
    # Real results require a separate human review; a model run alone cannot release.
    return 0 if report["summary"]["scripted_gate"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted", "real"], default="scripted")
    parser.add_argument("--authorize-real", action="store_true")
    parser.add_argument("--free-quota-confirmed", action="store_true")
    parser.add_argument("--total-token-limit", type=int, default=200000)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
