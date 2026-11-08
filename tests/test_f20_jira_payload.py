from dataclasses import replace
from uuid import UUID

import pytest

from opspilot.integrations.jira_payload import SandboxMapping, approval_digest, issue_payload


def test_destination_and_mapping_are_bound_to_approval():
    mapping = SandboxMapping("https://example.atlassian.net", "10000", "10001", 1)
    payload = issue_payload(mapping, UUID(int=1), summary="Incident", description="a\r\nb")
    assert payload == issue_payload(mapping, UUID(int=1), summary="Incident", description="a\nb")
    digest = approval_digest(mapping, payload)
    for other in (
        replace(mapping, site="https://other.atlassian.net"),
        replace(mapping, version=2),
        replace(mapping, project_id="20000"),
    ):
        assert approval_digest(other, payload) != digest
    assert approval_digest(mapping, payload + b" ") != digest


@pytest.mark.parametrize(
    "site",
    [
        "http://example.atlassian.net",
        "https://127.0.0.1",
        "https://example.atlassian.net/path",
        "https://example.atlassian.net@evil.test",
    ],
)
def test_reject_unregistered_site_shapes(site):
    with pytest.raises(ValueError, match="JIRA_MAPPING_INVALID"):
        SandboxMapping(site, "10000", "10001", 1)


def test_reject_control_characters_before_approval():
    mapping = SandboxMapping("https://example.atlassian.net", "10000", "10001", 1)
    with pytest.raises(ValueError, match="JIRA_SUMMARY_INVALID"):
        issue_payload(mapping, UUID(int=1), summary="a\nb", description="x")
