"""Fenced resource accounting. Only the database may grant a dispatch reservation."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from opspilot.agent.budgets import Budget, BudgetExceeded
from opspilot.llm.base import Usage
from opspilot.runtime.fencing import current_engine, current_fence


async def reserve(
    kind: str,
    identity: UUID | None = None,
    *,
    model: str = "scripted",
    tokens: int = 0,
    timeout_ms: int = 0,
) -> None:
    fence, engine = current_fence(), current_engine()
    if fence is None or engine is None:
        # Pure graph unit fixtures have no execution context. All persisted entry points
        # acquire an execution lease before invoking graph/provider/MCP work.
        return
    async with engine.begin() as conn:
        admitted = await conn.scalar(
            text("SELECT workflow.reserve_resource(:run,:kind,:id,:model,:tokens,:ms)"),
            {
                "run": fence.run,
                "kind": kind,
                "id": identity or uuid4(),
                "model": model,
                "tokens": tokens,
                "ms": timeout_ms,
            },
        )
    if not admitted:
        from opspilot.observability.client import count

        count("budget_denials", "source")
        raise BudgetExceeded(
            "Durable resource reservation denied",
            kind=f"durable_{kind}_reservation",
            requested=tokens if kind == "llm" else 1,
        )


async def settle(identity: UUID, usage: Usage, model: str | None, elapsed_ms: int) -> None:
    fence, engine = current_fence(), current_engine()
    if fence is None or engine is None:
        return
    # Newer model families with separate cache-write billing are not in the reviewed
    # price catalog. Unexpected billing dimensions never become a zero-cost estimate.
    async with engine.begin() as conn:
        accepted = await conn.scalar(
            text(
                "SELECT workflow.settle_provider(:run,:id,:inputs,:outputs,"
                ":cached,:model,:ms,:standard)"
            ),
            {
                "run": fence.run,
                "id": identity,
                "inputs": usage.input_tokens,
                "outputs": usage.output_tokens,
                "cached": usage.cached_input_tokens,
                "standard": usage.standard_pricing and not usage.cache_write_tokens,
                "model": model,
                "ms": min(120000, max(0, elapsed_ms)),
            },
        )
    if not accepted:
        raise RuntimeError("Provider settlement rejected")


async def synchronize(budget: Budget, *, save_elapsed: bool = False) -> None:
    fence, engine = current_fence(), current_engine()
    if fence is None or engine is None:
        return
    async with engine.begin() as conn:
        if save_elapsed:
            await conn.execute(
                text("SELECT workflow.record_active(:run,CAST(:elapsed AS numeric))"),
                {"run": fence.run, "elapsed": budget.snapshot()["active_seconds"]},
            )
        row: dict[str, Any] | None = await conn.scalar(
            text("SELECT workflow.usage_snapshot(:run)"), {"run": fence.run}
        )
    if row is None:
        raise BudgetExceeded("Usage scope is unavailable")
    for key in (
        "read_attempts",
        "llm_attempts",
        "rounds",
        "input_tokens",
        "output_tokens",
        "unknown_usage_count",
        "reserved_tokens",
    ):
        setattr(budget, key, row[key])
    budget.started = budget.clock() - max(
        budget.snapshot()["active_seconds"], row["active_seconds"]
    )
    budget.durable = {
        key: row[key]
        for key in (
            "cached_input_tokens",
            "known_spend_usd",
            "reserved_spend_usd",
            "cost_status",
            "price_versions",
            "currency",
        )
    }
