"""Offline F20 payload preparation. No transport or write capability is registered."""

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SandboxMapping:
    """Trusted admin configuration; sandbox ownership needs external verification."""

    site: str
    project_id: str
    issue_type_id: str
    version: int

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.atlassian\.net", self.site)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", self.project_id)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", self.issue_type_id)
            or type(self.version) is not int
            or self.version < 1
        ):
            raise ValueError("JIRA_MAPPING_INVALID")


def adf(text: str) -> dict[str, object]:
    """Preserve exact text, normalize only CRLF/CR to LF, never interpret markup."""
    if not text or len(text) > 16000 or any(ord(c) < 32 and c not in "\r\n\t" for c in text):
        raise ValueError("JIRA_TEXT_INVALID")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}] if line else []}
            for line in lines
        ],
    }


def issue_payload(
    mapping: SandboxMapping, operation_id: UUID, *, summary: str, description: str
) -> bytes:
    """Fixed field allowlist; caller must bind these bytes AND mapping to approval.

    A marker is correlation metadata, never a provider uniqueness guarantee.
    This helper does not authorize, persist, dispatch, or verify a write.
    """
    if not summary.strip() or len(summary) > 255 or any(ord(c) < 32 for c in summary):
        raise ValueError("JIRA_SUMMARY_INVALID")
    payload = {
        "fields": {
            "project": {"id": mapping.project_id},
            "issuetype": {"id": mapping.issue_type_id},
            "summary": summary,
            "description": adf(description),
        },
        "properties": [{"key": "opspilot.operation", "value": str(operation_id)}],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def approval_digest(mapping: SandboxMapping, payload: bytes) -> str:
    """Bind destination and mapping version as well as exact outbound bytes."""
    envelope = json.dumps(
        [mapping.site, mapping.project_id, mapping.issue_type_id, mapping.version],
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(envelope + b"\x00" + payload).hexdigest()
