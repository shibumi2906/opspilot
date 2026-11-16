"""Negative transport checks must reject unsafe input before DNS or socket use."""

from uuid import UUID

import pytest

from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.jira_payload import SandboxMapping
from opspilot.integrations.jira_transport import JiraEndpoint, request, route


@pytest.mark.parametrize(
    "kind,issue,comment",
    [
        ("delete_issue", "1", None),
        ("create_issue", "1", None),
        ("create_comment", "../1", None),
        ("read_issue", "KAN-1", None),
        ("read_comment", "1", "1?expand=all"),
        ("issue_marker", "1", "2"),
    ],
)
def test_routes_are_fixed(kind, issue, comment):
    with pytest.raises(ConnectorUnavailable):
        route(kind, issue, comment)


@pytest.mark.parametrize(
    "authorization,body",
    [
        ("Bearer anything", b"{}"),
        ("Basic x\r\nX-Leak: value", b"{}"),
        ("Basic x", None),
        ("Basic x", b"x" * 65537),
    ],
    ids=["auth_scheme", "header_injection", "missing_body", "oversize_body"],
)
def test_post_input_rejected_before_resolution(monkeypatch, authorization, body):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid input reached DNS")

    monkeypatch.setattr("socket.getaddrinfo", forbidden)
    endpoint = JiraEndpoint(
        SandboxMapping("https://example.atlassian.net", "1", "2", 1), ("8.8.8.8",)
    )
    with pytest.raises(ConnectorUnavailable):
        request(endpoint, authorization, "create_issue", body, None, None)


def test_mixed_dns_answers_are_rejected_before_tls(monkeypatch):
    endpoint = JiraEndpoint(
        SandboxMapping("https://example.atlassian.net", "1", "2", 1), ("8.8.8.8",), str(UUID(int=1))
    )
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))],
    )
    monkeypatch.setattr(
        "ssl.create_default_context", lambda: pytest.fail("Unapproved DNS answer reached TLS")
    )
    with pytest.raises(ConnectorUnavailable):
        request(endpoint, "Basic x", "read_issue", None, "1", None)


def test_comment_property_uses_global_comment_route():
    assert route("comment_marker", "123", "456") == (
        "GET",
        "/comment/456/properties/opspilot.operation",
    )
    with pytest.raises(ConnectorUnavailable):
        route("comment_marker", "../123", "456")
