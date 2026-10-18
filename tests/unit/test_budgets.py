import pytest

from opspilot.agent.budgets import Budget, BudgetExceeded, BudgetLimits


def test_verification_read_is_reserved():
    budget = Budget(BudgetLimits(reads=3))
    budget.begin_read()
    budget.begin_read()
    with pytest.raises(BudgetExceeded):
        budget.begin_read()
    assert budget.read_attempts == 2


@pytest.mark.parametrize("kind", ["round", "llm", "time", "tokens"])
def test_limits_stop_before_next_attempt(kind):
    now = [10.0]
    budget = Budget(
        BudgetLimits(rounds=1, llm_attempts=1, tokens=10, active_seconds=2), clock=lambda: now[0]
    )
    if kind == "round":
        budget.begin_round()
        action = budget.begin_round
    elif kind == "llm":
        budget.begin_llm()
        action = budget.begin_llm
    elif kind == "time":
        now[0] = 12
        action = budget.check
    else:
        budget.usage(7, 3)
        action = budget.check
    with pytest.raises(BudgetExceeded):
        action()


def test_missing_usage_remains_explicit():
    budget = Budget(BudgetLimits())
    budget.usage(None, None)
    assert budget.snapshot()["unknown_usage_count"] == 1
