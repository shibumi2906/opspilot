import argparse
import asyncio
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from opspilot.config import Settings
from opspilot.contracts.common import ToolResult
from opspilot.contracts.evidence import normalize_evidence
from opspilot.mcp_client.client import MCPClient


async def diagnose(settings: Settings, query: str, language: str) -> dict[str, Any]:
    run_id = uuid4()
    client = MCPClient(settings)
    results: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    missing = []
    async with client.session() as (session, _):
        await client.discover(session)

        async def call(name: str, arguments: dict[str, Any]) -> ToolResult:
            result = await client.call(session, name, arguments)
            results[name] = result.model_dump(mode="json")
            evidence.extend(
                e.model_dump(mode="json") for e in normalize_evidence(name, result, run_id)
            )
            if not result.ok:
                missing.append(name)
            return result

        lookup = await call("find_customers", {"query": query})
        if not lookup.ok or lookup.data is None:
            return {"outcome": "partial", "results": results, "missing_checks": missing}
        candidates = lookup.data["candidates"]
        # Prefer an exact name only when unique; never silently choose a partial candidate.
        exact = [c for c in candidates if c["name"].casefold() == query.casefold()]
        selected = exact if len(exact) == 1 else candidates
        if len(selected) != 1 or (lookup.data["truncated"] and not exact):
            return {"outcome": "insufficient_context", "results": results, "evidence": evidence}
        customer = await call("get_customer", {"customer_id": selected[0]["customer_id"]})
        if not customer.ok or customer.data is None or len(customer.data["integrations"]) != 1:
            return {"outcome": "insufficient_context", "results": results, "evidence": evidence}
        integration = customer.data["integrations"][0]
        scope = {
            "customer_id": customer.data["customer_id"],
            "integration_id": integration["integration_id"],
        }
        await call("get_service_status", scope)
        await call(
            "get_integration_events",
            scope
            | {
                "from": (settings.scenario_clock - timedelta(hours=2)).isoformat(),
                "to": settings.scenario_clock.isoformat(),
            },
        )
        search = {
            "query": "401",
            "integration_type": integration["integration_type"],
            "language": language,
        }
        await call("search_incidents", search)
        await call("search_documentation", search)
        await call("get_credential_status", scope)
    return {
        "outcome": "partial" if missing else "diagnosis_only",
        "synthetic": True,
        "results": results,
        "evidence": evidence,
        "missing_checks": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only synthetic MCP diagnosis; no LLM")
    parser.add_argument("query", nargs="?", default="GreenShop")
    parser.add_argument("--language", choices=("ru", "en"), default="ru")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(diagnose(Settings(), args.query, args.language)),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
