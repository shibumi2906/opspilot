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
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tenant": tenant,
        "run": run,
        "logical_action": logical,
        "revision": revision,
        "version": version,
        "plan_version": plan_version,
        "tool": "create_ticket",
        "backend": "local",
        "connector": "local",
        "customer": str(arguments["customer_id"]),
        "arguments": arguments,
        "evidence_refs": arguments["evidence_ids"],
        "preconditions": {"customer": str(arguments["customer_id"])},
        "risk": "high" if arguments["priority"] == "high" else "medium",
        "dependencies": [],
        "expires_at": expires.astimezone(UTC).isoformat(),
    }


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
    )
    return bool(
        action.revision_document == expected and action.revision_hash == canonical_hash(expected)
    )
