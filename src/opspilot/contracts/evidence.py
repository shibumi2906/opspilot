import json
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime

from opspilot.contracts.common import StrictModel, ToolResult
from opspilot.mcp_client.registry import READ_TOOLS

STANDALONE_NAMESPACE = UUID(int=0)


class Evidence(StrictModel):
    evidence_id: str
    tool_name: str
    tool_call_id: UUID
    observed_at: AwareDatetime
    source_type: str
    source_id: str
    source_version: str | None = None
    customer_id: UUID | None = None
    excerpt: str
    data_hash: str
    facts: dict[str, Any]


def normalize_evidence(
    tool_name: str, result: ToolResult, run_id: UUID = STANDALONE_NAMESPACE
) -> list[Evidence]:
    contract = READ_TOOLS[tool_name]
    if not result.ok:
        return []
    data = contract.data.model_validate(result.data).model_dump(mode="json")
    items = data.get("hits", data.get("events", data.get("candidates")))
    evidence = []
    for source in result.sources:
        facts: dict[str, Any] | None = data
        if items is not None:
            facts = next(
                (
                    item
                    for item in items
                    if source.source_id
                    in (
                        str(item.get(k))
                        for k in ("incident_id", "article_id", "event_id", "customer_id")
                    )
                ),
                None,
            )
            if facts is None:
                raise ValueError("Source does not match returned data")
        assert facts is not None
        content = json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        data_hash = sha256(content.encode()).hexdigest()
        identity = f"{run_id}:{source.source_type}:{source.source_id}:{source.version}:{data_hash}"
        digest = sha256(identity.encode()).hexdigest()
        evidence.append(
            Evidence(
                evidence_id=f"ev_{digest}",
                tool_name=tool_name,
                tool_call_id=result.tool_call_id,
                observed_at=result.observed_at,
                source_type=source.source_type,
                source_id=source.source_id,
                source_version=source.version,
                customer_id=facts.get("customer_id"),
                excerpt=content[:600],
                data_hash=data_hash,
                facts=facts,
            )
        )
    return evidence
