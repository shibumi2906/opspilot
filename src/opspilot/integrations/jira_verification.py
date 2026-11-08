"""Pure exact-match rules. Vendor normalization is explicit; search absence is not proof.

No network calls, retry logic, approval authority or capability registration here.
"""

import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from opspilot.integrations.jira_payload import SandboxMapping


class Outcome(StrEnum):
    VERIFIED = "verified"
    UNKNOWN = "unknown"
    NEEDS_ATTENTION = "needs_attention"


def normalize_adf(document: object) -> object:
    """Only Jira-generated paragraph localId attributes may be ignored.

    All text, marks, order, links and other attributes participate in comparison.
    Identity/version must remain present. Unsupported transformations fail exact match.
    """
    if isinstance(document, list):
        return [normalize_adf(v) for v in document]
    if isinstance(document, dict):
        result = {}
        for key, value in document.items():
            if key == "attrs" and document.get("type") == "paragraph" and isinstance(value, dict):
                attrs = {k: v for k, v in value.items() if k != "localId"}
                if attrs:
                    result[key] = normalize_adf(attrs)
            else:
                result[key] = normalize_adf(value)
        return result
    return document


def issue_matches(
    mapping: SandboxMapping,
    outbound: bytes,
    observed: dict[str, Any],
    *,
    property_value: object,
    operation_id: UUID,
) -> bool:
    prepared = json.loads(outbound)
    if prepared.get("properties") != [{"key": "opspilot.operation", "value": str(operation_id)}]:
        return False
    expected = prepared["fields"]
    fields = observed.get("fields", {})
    if not isinstance(fields, dict):
        return False
    project, issue_type = fields.get("project"), fields.get("issuetype")
    return bool(
        isinstance(observed.get("id"), str)
        and observed["id"].isascii()
        and observed["id"].isdigit()
        and isinstance(project, dict)
        and project.get("id") == mapping.project_id
        and isinstance(issue_type, dict)
        and issue_type.get("id") == mapping.issue_type_id
        and fields.get("summary") == expected["summary"]
        and normalize_adf(fields.get("description")) == normalize_adf(expected["description"])
        and property_value == str(operation_id)
    )


def comment_matches(
    outbound: bytes, observed: dict[str, Any], *, property_value: object, operation_id: UUID
) -> bool:
    """Caller must independently establish exact issue destination before this check."""
    prepared = json.loads(outbound)
    return bool(
        prepared.get("properties") == [{"key": "opspilot.operation", "value": str(operation_id)}]
        and isinstance(observed.get("id"), str)
        and observed["id"].isascii()
        and observed["id"].isdigit()
        and normalize_adf(observed.get("body")) == normalize_adf(prepared["body"])
        and property_value == str(operation_id)
    )


def reconciliation(matches: list[bool], *, complete: bool) -> Outcome:
    """A bounded search is positive evidence only if complete and exactly one exact match.

    Zero eventually consistent matches never authorize a fresh dispatch. Multiple
    marker matches need attention even when only one has the expected content.
    """
    if len(matches) > 1:
        return Outcome.NEEDS_ATTENTION
    if len(matches) == 1 and complete and matches[0]:
        return Outcome.VERIFIED
    if matches and not matches[0]:
        return Outcome.NEEDS_ATTENTION
    return Outcome.UNKNOWN
