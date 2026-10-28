"""Canonical purpose-bound revision digest, independent of ORM and transport."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def canonical_hash(document: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def document(
    *,
    tenant: str,
    run: str,
    logical: str,
    revision: str,
    version: int,
    arguments: dict[str, Any],
    expires: datetime,
    plan_version: int = 1,
    tool: str = "create_ticket",
    plan_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool not in {"create_ticket", "add_ticket_comment", "notify_manager"}:
        raise ValueError("Unsupported local operation")
    target = {"customer": str(arguments["customer_id"])}
    if tool == "add_ticket_comment":
        target["ticket"] = str(arguments["ticket_id"])
    if tool == "notify_manager":
        target["recipient"] = str(arguments["recipient_id"])
    result = {
        "schema_version": 1,
        "tenant": tenant,
        "run": run,
        "logical_action": logical,
        "revision": revision,
        "version": version,
        "plan_version": plan_version,
        "tool": tool,
        "backend": "local",
        "connector": "local",
        "customer": str(arguments["customer_id"]),
        "arguments": arguments,
        "evidence_refs": arguments["evidence_ids"],
        "preconditions": target,
        "risk": "high" if arguments.get("priority") == "high" else "medium",
        "dependencies": [],
        "expires_at": expires.astimezone(UTC).isoformat(),
    }

    if plan_binding is not None:
        result["plan"] = plan_binding
        result["dependencies"] = plan_binding["dependencies"]
    return result


def valid_revision(action: Any) -> bool:
    expected = document(
        tenant=str(action.tenant_id),
        run=str(action.run_id),
        logical=str(action.logical_action_id),
        revision=str(action.id),
        version=action.revision_number,
        plan_version=action.plan_version,
        arguments=action.arguments,
        expires=action.expires_at,
        tool=action.tool_name,
        plan_binding=getattr(action, "plan_binding", None),
    )
    return bool(
        action.revision_document == expected and action.revision_hash == canonical_hash(expected)
    )
