import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from opspilot.agent.budgets import Budget
from opspilot.agent.evidence import missing_reads
from opspilot.agent.policy import PolicyViolation
from opspilot.agent.state import AgentState
from opspilot.config import Settings
from opspilot.contracts.common import ToolError, ToolResult
from opspilot.contracts.evidence import normalize_evidence
from opspilot.llm.base import Operation, Provider, ProviderFailure, Usage
from opspilot.mcp_client.client import MCPClient
from opspilot.mcp_client.registry import READ_TOOLS
from opspilot.telemetry import span

T = TypeVar("T", bound=BaseModel)


class Runtime:
    """Non-serializable dependencies and counters live outside the checkpoint state."""

    def __init__(
        self,
        settings: Settings,
        provider: Provider,
        budget: Budget,
        on_update: Callable[[AgentState], Awaitable[None]] | None = None,
    ) -> None:
        self.on_update = on_update
        self.settings = settings
        self.provider = provider
        self.budget = budget
        self.client = MCPClient(settings)

    async def llm(
        self, operation: Operation, context: dict[str, Any], model: type[T], state: AgentState
    ) -> T:
        for attempt in range(1, 3):
            self.budget.begin_llm()
            call_id = str(uuid4())
            usage = Usage()
            state.setdefault("llm_calls", {})[call_id] = {
                "operation": operation,
                "attempt": attempt,
                "status": "started",
            }
            try:
                async with asyncio.timeout(min(30, self.budget.remaining())):
                    with span(
                        "llm.request", operation=operation, run_id=state["run_id"]
                    ) as current:
                        completion = await self.provider.complete(operation, context)
                        for key, value in completion.usage.model_dump().items():
                            if value is not None:
                                current.set_attribute(key, value)
                usage = completion.usage
                if completion.model_id:
                    state["model_id"] = completion.model_id
                output = model.model_validate(completion.output)
            except (ValidationError, ProviderFailure, TimeoutError) as exc:
                if isinstance(exc, ProviderFailure):
                    usage = exc.usage
                code = (
                    exc.code
                    if isinstance(exc, ProviderFailure)
                    else (
                        "PROVIDER_TIMEOUT"
                        if isinstance(exc, TimeoutError)
                        else "INVALID_STRUCTURED_OUTPUT"
                    )
                )
                state["llm_calls"][call_id].update(status="failed", code=code)
                retryable = not isinstance(exc, ProviderFailure) or exc.retryable
                if attempt == 2 or not retryable:
                    raise ProviderFailure(code) from None
                context = context | {
                    "correction": "Previous response was invalid or unavailable; follow the schema."
                }
            else:
                state["llm_calls"][call_id]["status"] = "completed"
                return output
            finally:
                self.budget.usage(usage.input_tokens, usage.output_tokens)
                state["llm_calls"][call_id]["usage"] = usage.model_dump()
                self.budget.check()
        raise AssertionError("Unreachable provider attempt")

    async def read(
        self,
        name: str,
        arguments: dict[str, Any],
        state: AgentState,
        call_id: str | None = None,
        *,
        verification: bool = False,
    ) -> ToolResult:
        if name not in READ_TOOLS:
            raise PolicyViolation("Unknown read tool")
        arguments = (
            READ_TOOLS[name]
            .arguments.model_validate(arguments)
            .model_dump(mode="json", by_alias=True)
        )
        call_id = call_id or str(uuid4())
        for attempt in range(1, 4):
            self.budget.begin_read(verification=verification)
            key = f"{call_id}:{attempt}"
            state.setdefault("tool_calls", {})[key] = {
                "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "tool_call_id": call_id,
                "name": name,
                "arguments": arguments,
                "attempt": attempt,
                "status": "started",
            }
            try:
                async with asyncio.timeout(min(5, self.budget.remaining())):
                    async with self.client.session() as (session, _):
                        result = await self.client.call(session, name, arguments)
            except Exception:
                # Transport exceptions may contain headers or DSNs. Persist only a safe code.
                result = ToolResult(
                    ok=False,
                    observed_at=self.settings.scenario_clock,
                    error=ToolError(
                        code="DEPENDENCY_UNAVAILABLE",
                        message="MCP source unavailable",
                        retryable=True,
                    ),
                )
            result = result.model_copy(update={"tool_call_id": UUID(call_id)})
            state["tool_calls"][key].update(
                status="completed" if result.ok else "failed",
                error=result.error.model_dump() if result.error else None,
            )
            if result.ok or result.error is None or not result.error.retryable or attempt == 3:
                break
            delay = min(
                0.05 * 2 ** (attempt - 1) + random.uniform(0, 0.02), self.budget.remaining()
            )
            if delay > 0:
                await asyncio.sleep(delay)
        state.setdefault("observations", {})[call_id] = {
            "name": name,
            "arguments": arguments,
            "result": result.model_dump(mode="json"),
        }
        state.setdefault("evidence", {}).update(
            {
                e.evidence_id: e.model_dump(mode="json")
                for e in normalize_evidence(name, result, UUID(state["run_id"]))
            }
        )
        self.budget.check()
        return result

    def context(self, state: AgentState, operation: Operation = "investigate") -> dict[str, Any]:
        # Send each observation once; provenance hashes and duplicate raw results stay local.
        keys = (
            "request",
            "language",
            "intent",
            "customer_id",
            "customer_name",
            "integration_id",
            "integration_type",
            "time_window",
        )
        data = {key: state.get(key) for key in keys}
        if operation == "investigate":
            data["observations"] = {
                str(index): {
                    "name": value["name"],
                    "result": {
                        "ok": value["result"]["ok"],
                        "data": value["result"]["data"],
                        "error": value["result"]["error"],
                    },
                }
                for index, value in enumerate(state.get("observations", {}).values())
            }
        elif operation == "reason":
            data["evidence"] = {
                identity: {
                    key: value[key] for key in ("source_type", "source_id", "observed_at", "facts")
                }
                for identity, value in state.get("evidence", {}).items()
            }
        return {"state": data, "missing_reads": missing_reads(state)}
