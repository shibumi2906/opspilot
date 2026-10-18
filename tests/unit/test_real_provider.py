import json

import httpx
import pytest

from opspilot.config import Settings
from opspilot.llm.base import ProviderFailure
from opspilot.llm.real import RealProvider
from opspilot.mcp_client.registry import READ_TOOLS


def settings():
    return Settings(
        _env_file=None,
        mcp_service_token="a" * 64,
        openai_api_key="fake-test-key",
        openai_model="gpt-5.6",
    )


async def test_real_adapter_sends_tools_and_parses_function_call():
    def handler(request):
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["model"] == "gpt-5.6" and body["store"] is False
        assert {t["name"] for t in body["tools"]} == set(READ_TOOLS)
        assert "create_ticket" not in request.content.decode()
        assert body["parallel_tool_calls"] is False
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {"input_tokens": 12, "output_tokens": 4},
                "output": [
                    {
                        "type": "function_call",
                        "name": "get_service_status",
                        "arguments": '{"customer_id":"x","integration_id":"y"}',
                    }
                ],
            },
        )

    result = await RealProvider(settings(), transport=httpx.MockTransport(handler)).complete(
        "investigate", {"state": {}}
    )
    assert result.output["calls"][0]["name"] == "get_service_status"
    assert result.usage.input_tokens == 12


async def test_real_adapter_structured_output_and_missing_usage():
    def handler(request):
        body = json.loads(request.content)
        schema = body["text"]["format"]
        assert schema["type"] == "json_schema" and schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"proposal": null}'}],
                    }
                ],
            },
        )

    result = await RealProvider(settings(), transport=httpx.MockTransport(handler)).complete(
        "plan", {}
    )
    assert result.output == {"proposal": None}
    assert result.usage.input_tokens is None


@pytest.mark.parametrize("status", [401, 429, 503])
async def test_provider_errors_do_not_leak_response(status):
    provider = RealProvider(
        settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="SECRET_RESPONSE_BODY")
        ),
    )
    with pytest.raises(ProviderFailure) as error:
        await provider.complete("plan", {})
    assert "SECRET" not in str(error.value)
    assert error.value.retryable == (status != 401)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": [{"content": [{"type": "refusal"}]}]},
        {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "bad"}]}]},
    ],
)
async def test_refusal_incomplete_and_invalid_json_fail_closed(body):
    provider = RealProvider(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    with pytest.raises(ProviderFailure):
        await provider.complete("plan", {})
