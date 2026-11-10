from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from opspilot.agent import runtime
from opspilot.agent.budgets import Budget, BudgetExceeded, BudgetLimits
from opspilot.config import Settings
from opspilot.llm.base import Completion, ProviderFailure, Usage


class Output(BaseModel):
    answer: str


async def test_completed_response_is_returned_at_token_boundary():
    provider = AsyncMock()
    provider.complete.return_value = Completion(
        output={"answer": "ok"}, usage=Usage(input_tokens=1, output_tokens=1)
    )
    agent = runtime.Runtime(Settings(), provider, Budget(BudgetLimits(tokens=2)))
    assert (await agent.llm("classify", {}, Output, {"run_id": "test"})).answer == "ok"
    with pytest.raises(BudgetExceeded) as stop:
        await agent.llm("classify", {}, Output, {"run_id": "test"})
    assert stop.value.details == {"kind": "tokens", "used": 2, "available": 0}
    provider.complete.assert_awaited_once()


@pytest.mark.parametrize("settlement_fails", [False, True])
async def test_pre_dispatch_denial_keeps_provider_error_and_settles_zero(
    monkeypatch, settlement_fails
):
    failure = ProviderFailure("EVAL_GLOBAL_TOKEN_LIMIT", dispatched=False)
    provider = AsyncMock()
    provider.complete.side_effect = failure
    settlement = AsyncMock(side_effect=RuntimeError() if settlement_fails else None)
    monkeypatch.setattr(runtime, "settle", settlement)
    agent = runtime.Runtime(Settings(), provider, Budget(BudgetLimits()))
    state = {"run_id": "test"}
    with pytest.raises(ProviderFailure) as caught:
        await agent.llm("classify", {}, Output, state)
    assert caught.value is failure
    usage = settlement.await_args.args[1]
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)
    assert agent.budget.unknown_usage_count == 0
    call = next(iter(state["llm_calls"].values()))
    assert call["dispatched"] is False
    assert ("accounting_error" in call) is settlement_fails
