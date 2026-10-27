"""Real worker fault fixture; production fencing remains enabled for every probe."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.base import empty_checkpoint
from psycopg import Error as PsycopgError
from sqlalchemy import text

from opspilot.agent.budgets import Budget, BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.runtime import Runtime
from opspilot.agent.state import Classification
from opspilot.auth.execution import execution_scope
from opspilot.auth.service_context import action_scope
from opspilot.llm.scripted import ScriptedProvider
from opspilot.mcp_client.client import MCPClient
from opspilot.runtime.fencing import current_fence
from opspilot.runtime.run_service import RunService
from opspilot.runtime.worker import main

original = RunService.execute


async def probe(self, run):
    rejected = []
    async with execution_scope(self.engine, run):
        for label, sql in [
            (
                "projection",
                "UPDATE workflow.agent_runs SET public_snapshot=jsonb_build_object('stale',true) "
                "WHERE id=:r",
            ),
            ("action", "UPDATE workflow.actions SET execution_status='failed' WHERE run_id=:r"),
            (
                "approval",
                "UPDATE workflow.approvals SET decision='rejected' "
                "WHERE action_id IN (SELECT id FROM workflow.actions WHERE run_id=:r)",
            ),
        ]:
            try:
                async with self.engine.begin() as conn:
                    await conn.execute(text(sql), {"r": run})
            except Exception as exc:
                if getattr(getattr(exc, "orig", None), "sqlstate", None) == "40001":
                    rejected.append(label)
        runtime = Runtime(self.settings, ScriptedProvider(), Budget(BudgetLimits()))
        for label, call in [
            (
                "read_dispatch",
                lambda: runtime.read(
                    "get_customer", {"customer_id": "00000000-0000-0000-0000-000000000001"}, {}
                ),
            ),
            ("model_dispatch", lambda: runtime.llm("classify", {}, Classification, {})),
        ]:
            try:
                await call()
            except Exception as exc:
                if getattr(getattr(exc, "orig", None), "sqlstate", None) == "40001":
                    rejected.append(label)
        async with postgres_checkpointer(self.settings) as saver:
            cp = empty_checkpoint()
            cp["channel_values"] = {"late": {"forbidden": True}}
            config = {
                "configurable": {
                    "thread_id": str(run),
                    "checkpoint_ns": "",
                    "checkpoint_id": cp["id"],
                }
            }
            for label, call in [
                (
                    "checkpoint",
                    lambda: saver.aput(
                        config, cp, {"source": "update", "step": 0, "parents": {}}, {"late": "late"}
                    ),
                ),
                (
                    "pending_writes",
                    lambda: saver.aput_writes(
                        config, [("late", {"forbidden": True})], str(uuid4())
                    ),
                ),
            ]:
                try:
                    await call()
                except Exception as exc:
                    if getattr(exc, "sqlstate", None) == "40001":
                        rejected.append(label)
        async with self.engine.connect() as conn:
            action = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,arguments,arguments_hash FROM workflow.actions "
                            "WHERE run_id=:r"
                        ),
                        {"r": run},
                    )
                )
                .mappings()
                .one()
            )
        client = MCPClient(self.settings)
        with action_scope(str(run), str(action["id"]), action["arguments_hash"]):
            try:
                async with client.session() as (session, _):
                    result = await client.call(
                        session,
                        "create_ticket",
                        {
                            "run_id": str(run),
                            "action_id": str(action["id"]),
                            "arguments": action["arguments"],
                        },
                    )
                if (
                    not result.ok
                    and result.error.code == "STATE_CONFLICT"
                    and not result.error.retryable
                ):
                    rejected.append("operation")
            except Exception as exc:
                # F09 rejects stale Core issuance before a request can reach MCP.
                # The same DB fence SQLSTATE is required; arbitrary failures do not pass.
                state = getattr(exc, "sqlstate", None) or getattr(
                    getattr(exc, "orig", None), "sqlstate", None
                )
                if state == "40001":
                    rejected.append("operation")
    return rejected


async def delayed(self, run, *args, **kwargs):
    fence = current_fence()
    if str(run) == os.environ["F06_RUN"] and fence and fence.epoch == 1:

        async def pause():
            print(
                json.dumps(
                    {
                        "claimed": str(run),
                        "owner": str(fence.owner),
                        "epoch": fence.epoch,
                        "held_sdk_transaction": os.environ.get("F06_HOLD_SDK") == "1",
                    }
                ),
                flush=True,
            )
            await asyncio.sleep(120)

        try:
            if os.environ.get("F06_HOLD_SDK") == "1":
                async with (
                    execution_scope(self.engine, run),
                    postgres_checkpointer(self.settings) as saver,
                ):
                    async with saver._cursor(pipeline=True):
                        await pause()
            else:
                await pause()
        except (asyncio.CancelledError, PsycopgError):
            # Deliberately ignore cancellation long enough to simulate a late callback.
            while not await asyncio.to_thread(Path(os.environ["F06_RELEASE"]).exists):  # noqa: ASYNC110 - cross-process barrier
                await asyncio.sleep(0.05)
            rejected = await probe(self, run)
            print(json.dumps({"late_rejected": rejected, "epoch": fence.epoch}), flush=True)
            raise asyncio.CancelledError() from None
    return await original(self, run, *args, **kwargs)


RunService.execute = delayed
asyncio.run(main())
