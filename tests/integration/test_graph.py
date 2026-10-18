from uuid import uuid4

import pytest
from sqlalchemy import text

from opspilot.agent.budgets import BudgetLimits
from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.agent.service import RunConflict, run_investigation
from opspilot.llm.base import Completion, Usage
from opspilot.llm.scripted import ScriptedProvider


@pytest.fixture(autouse=True)
async def no_business_writes(admin_engine):
    async with admin_engine.connect() as conn:
        before = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM domain.tickets), "
                    "(SELECT count(*) FROM workflow.actions), "
                    "(SELECT count(*) FROM workflow.approvals)"
                )
            )
        ).one()
    yield
    async with admin_engine.connect() as conn:
        after = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM domain.tickets), "
                    "(SELECT count(*) FROM workflow.actions), "
                    "(SELECT count(*) FROM workflow.approvals)"
                )
            )
        ).one()
    assert after == before


@pytest.mark.parametrize(
    "user_text,language",
    [
        ("Расследуй, почему у GreenShop сегодня не приходят заказы", "ru"),
        ("Investigate why GreenShop orders fail today", "en"),
    ],
)
async def test_graph_proposal_and_durable_checkpoint(
    integration_settings, admin_engine, user_text, language
):
    result = await run_investigation(integration_settings, user_text, mode="scripted")
    assert result["outcome"] == "proposed_only", result
    assert result["mode"] == "scripted" and result["language"] == language
    assert result["proposed_action"]["customer_id"] == "00000000-0000-0000-0000-000000000001"
    assert result["final_report"]["verification_status"] == "not_started"
    assert result["final_report"]["ticket_id"] is None
    assert result["hypotheses"]
    assert result["budget"]["read_attempts"] == 7
    assert result["budget"]["llm_attempts"] == 6
    async with postgres_checkpointer(integration_settings) as saver:
        checkpoint = await saver.aget_tuple({"configurable": {"thread_id": result["run_id"]}})
        assert checkpoint is not None
        values = checkpoint.checkpoint["channel_values"]
        assert values["run_id"] == values["thread_id"] == result["run_id"]
        assert values["final_report"] == result["final_report"]
        assert {v["name"] for v in values["observations"].values()} == {
            "find_customers",
            "get_customer",
            "get_service_status",
            "get_integration_events",
            "get_credential_status",
            "search_incidents",
            "search_documentation",
        }
        assert len(values["evidence"]) == len(set(values["evidence"]))
    async with admin_engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM checkpoints.checkpoints WHERE thread_id=:id"),
            {"id": result["run_id"]},
        )
    assert count >= 10
    for fact in result["final_report"]["facts"]:
        assert set(fact["evidence_ids"]) <= result["evidence"].keys()
    assert integration_settings.mcp_service_token.get_secret_value() not in str(result)


@pytest.mark.parametrize(
    "user_text,outcome",
    [
        ("Check GreenShop status", "diagnosis_only"),
        ("Investigate customer MissingShop", "insufficient_context"),
        ("Investigate Green", "insufficient_context"),
        ("Investigate the incident", "insufficient_context"),
        ("Delete GreenShop", "blocked"),
    ],
)
async def test_conditional_paths(integration_settings, user_text, outcome):
    result = await run_investigation(integration_settings, user_text, mode="scripted")
    assert result["outcome"] == outcome, result
    assert result["proposed_action"] is None
    if "status" in user_text:
        assert result["budget"]["read_attempts"] == 3
    if outcome == "blocked":
        assert result["budget"]["llm_attempts"] == result["budget"]["read_attempts"] == 0


@pytest.mark.parametrize(
    "overlay_settings,outcome",
    [
        ("healthy", "diagnosis_only"),
        ("unknown", "partial"),
        ("contradictory", "partial"),
        ("timeout", "partial"),
    ],
    indirect=["overlay_settings"],
)
async def test_monitoring_gates(overlay_settings, outcome):
    result = await run_investigation(overlay_settings, "Investigate GreenShop", mode="scripted")
    assert result["outcome"] == outcome, result
    assert result["proposed_action"] is None
    if overlay_settings.scenario_id in ("unknown", "timeout"):
        assert not result["hypotheses"]
        assert not any("expired" in f["statement"] for f in result["final_report"]["facts"])
    if overlay_settings.scenario_id == "timeout":
        assert "get_service_status" in result["final_report"]["missing_checks"]
        assert result["budget"]["read_attempts"] == 5  # lookup/customer + three failed attempts


class MaliciousProvider(ScriptedProvider):
    def __init__(self, name):
        self.name = name

    async def complete(self, operation, context):
        if operation == "investigate":
            return Completion(
                output={"stop": False, "calls": [{"name": self.name, "arguments": {}}]},
                usage=Usage(input_tokens=1, output_tokens=1),
            )
        return await super().complete(operation, context)


@pytest.mark.parametrize("name", ["unknown_tool", "create_ticket"])
async def test_model_cannot_dispatch_unknown_or_write_tool(integration_settings, name):
    result = await run_investigation(
        integration_settings,
        "Investigate GreenShop",
        mode="scripted",
        provider=MaliciousProvider(name),
    )
    assert result["outcome"] == "blocked"
    assert result["budget"]["read_attempts"] == 2
    assert result["errors"]["investigate"]["code"] == "POLICY_VIOLATION"


class EndlessProvider(ScriptedProvider):
    async def complete(self, operation, context):
        if operation == "investigate":
            state = context["state"]
            return Completion(
                output={
                    "stop": False,
                    "calls": [
                        {
                            "name": "get_service_status",
                            "arguments": {
                                "customer_id": state["customer_id"],
                                "integration_id": state["integration_id"],
                            },
                        }
                    ],
                },
                usage=Usage(input_tokens=0, output_tokens=0),
            )
        return await super().complete(operation, context)


@pytest.mark.parametrize(
    "limits,provider",
    [
        (BudgetLimits(reads=2), ScriptedProvider()),
        (BudgetLimits(llm_attempts=1), ScriptedProvider()),
        (BudgetLimits(rounds=2), EndlessProvider()),
    ],
)
async def test_exhausted_budgets_stop_without_proposal(integration_settings, limits, provider):
    result = await run_investigation(
        integration_settings,
        "Investigate GreenShop",
        mode="scripted",
        provider=provider,
        limits=limits,
    )
    assert result["outcome"] == "budget_exhausted"
    assert result["proposed_action"] is None
    assert result["budget"]["read_attempts"] <= limits.reads - 1
    assert result["budget"]["llm_attempts"] <= limits.llm_attempts


async def test_client_request_id_is_idempotent(integration_settings):
    key = uuid4()
    first = await run_investigation(
        integration_settings, "Investigate GreenShop", mode="scripted", client_request_id=key
    )
    assert (
        await run_investigation(
            integration_settings, "Investigate GreenShop", mode="scripted", client_request_id=key
        )
        == first
    )
    with pytest.raises(RunConflict):
        await run_investigation(
            integration_settings, "Check GreenShop status", mode="scripted", client_request_id=key
        )


class ExcessiveUsageProvider(ScriptedProvider):
    async def complete(self, operation, context):
        result = await super().complete(operation, context)
        return result.model_copy(update={"usage": Usage(input_tokens=30000, output_tokens=1)})


class InvalidOutputProvider:
    async def complete(self, operation, context):
        return Completion(output={}, usage=Usage())


@pytest.mark.parametrize(
    "provider,outcome,attempts",
    [
        (ExcessiveUsageProvider(), "budget_exhausted", 1),
        (InvalidOutputProvider(), "partial", 2),
    ],
)
async def test_usage_and_invalid_output_accounting(
    integration_settings, provider, outcome, attempts
):
    result = await run_investigation(
        integration_settings, "Investigate GreenShop", mode="scripted", provider=provider
    )
    assert result["outcome"] == outcome
    assert result["proposed_action"] is None
    assert result["budget"]["llm_attempts"] == attempts
    assert result["budget"]["read_attempts"] == 0
    if outcome == "partial":
        assert result["budget"]["unknown_usage_count"] == 2


class BadReasonProvider(ScriptedProvider):
    async def complete(self, operation, context):
        result = await super().complete(operation, context)
        if operation == "reason":
            result.output["hypotheses"][0]["supporting_evidence_ids"] = ["fabricated-source"]
        return result


async def test_unknown_hypothesis_reference_blocks_proposal(integration_settings):
    result = await run_investigation(
        integration_settings, "Investigate GreenShop", mode="scripted", provider=BadReasonProvider()
    )
    assert result["outcome"] == "blocked"
    assert result["proposed_action"] is None
