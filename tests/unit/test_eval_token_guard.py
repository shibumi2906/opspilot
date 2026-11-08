import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opspilot.evals.token_guard import TokenGuard
from opspilot.llm.base import Completion, ProviderFailure, Usage
from opspilot.llm.real import RealProvider


async def test_total_reservation_blocks_before_dispatch_and_is_durable(tmp_path):
    path = tmp_path / "ledger.json"
    guard = TokenGuard(path, 100, "fixed")
    provider = SimpleNamespace(model="fixed", reservation_tokens=lambda *args: 80)
    index = await guard.reserve(provider, "classify", {})
    assert json.loads(path.read_text())["charged_or_reserved"] == 80
    await guard.settle(index, Usage(input_tokens=30, output_tokens=10))
    assert guard.charged == 40
    with pytest.raises(ProviderFailure, match="GLOBAL_TOKEN_LIMIT"):
        await guard.reserve(provider, "reason", {})
    assert len(guard.entries) == 1
    assert guard.charged == 40
    with pytest.raises(FileExistsError):
        TokenGuard(path, 100, "fixed")


async def test_unknown_usage_keeps_reservation_and_stops_further_calls(tmp_path):
    guard = TokenGuard(tmp_path / "ledger.json", 100, "fixed")
    provider = SimpleNamespace(model="fixed", reservation_tokens=lambda *args: 20)
    index = await guard.reserve(provider, "classify", {})
    await guard.settle(index, Usage())
    assert guard.charged == 20
    assert guard.snapshot()["unknown_usage"] == 1
    with pytest.raises(ProviderFailure, match="UNKNOWN_PROVIDER_USAGE"):
        await guard.reserve(provider, "reason", {})
    assert len(guard.entries) == 1


async def test_changed_model_cannot_spend_quota(tmp_path):
    guard = TokenGuard(tmp_path / "ledger.json", 100, "fixed")
    provider = SimpleNamespace(model="other", reservation_tokens=lambda *args: 20)
    with pytest.raises(ProviderFailure, match="MODEL_CONFIG_CHANGED"):
        await guard.reserve(provider, "reason", {})
    assert guard.charged == 0


def test_refuse_budget_over_owner_cap(tmp_path):
    with pytest.raises(ValueError):
        TokenGuard(tmp_path / "ledger.json", 200001, "fixed")


async def test_installed_guard_bounds_all_provider_instances_before_transport(tmp_path):
    calls = []

    async def fake_complete(provider, operation, context):
        calls.append(operation)
        return Completion(output={}, usage=Usage(input_tokens=20, output_tokens=10))

    guard = TokenGuard(tmp_path / "ledger.json", 65, "fixed")
    one, two = object.__new__(RealProvider), object.__new__(RealProvider)
    one.model = two.model = "fixed"
    with (
        patch.object(RealProvider, "complete", fake_complete),
        patch.object(RealProvider, "reservation_tokens", lambda *args: 35),
        guard.installed(),
    ):
        await one.complete("classify", {})
        await two.complete("reason", {})
        with pytest.raises(ProviderFailure, match="GLOBAL_TOKEN_LIMIT"):
            await one.complete("plan", {})
    assert calls == ["classify", "reason"]
    assert guard.snapshot()["known_input_tokens"] == 40
    assert guard.charged == 60
