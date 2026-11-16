"""Bounded Jira HTTPS transport. Callers authorize and persist each dispatch first."""

import http.client
import re
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from loguru import logger

from opspilot.integrations.egress import ConnectorUnavailable, validate_addresses
from opspilot.integrations.executor import bounded
from opspilot.integrations.jira_payload import SandboxMapping
from opspilot.integrations.prometheus.transport import decode

MAX_BYTES = 131072


@dataclass(frozen=True)
class JiraEndpoint:
    mapping: SandboxMapping
    addresses: tuple[str, ...]
    cloud_id: str | None = None

    @property
    def host(self) -> str:
        return "api.atlassian.com" if self.cloud_id else self.mapping.site.removeprefix("https://")

    @property
    def prefix(self) -> str:
        if self.cloud_id is None:
            return "/rest/api/3"
        if not re.fullmatch(r"[a-f0-9-]{36}", self.cloud_id):
            raise ConnectorUnavailable()
        return "/ex/jira/" + self.cloud_id + "/rest/api/3"


def numeric(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ConnectorUnavailable()
    return value


def route(kind: str, issue: str | None = None, comment: str | None = None) -> tuple[str, str]:
    if kind == "create_issue" and issue is None and comment is None:
        return "POST", "/issue"
    if kind == "read_issue" and issue is not None and comment is None:
        return "GET", "/issue/" + numeric(issue) + "?fields=project,issuetype,summary,description"
    if kind == "issue_marker" and issue is not None and comment is None:
        return "GET", "/issue/" + numeric(issue) + "/properties/opspilot.operation"
    if kind == "find_issues" and issue is not None and comment is None:
        return "GET", "/search/jql?jql=project%3D" + numeric(issue) + "&maxResults=10&fields=id"
    if kind == "find_comments" and issue is not None and comment is None:
        return "GET", "/issue/" + numeric(issue) + "/comment?maxResults=10&startAt=0"
    if kind == "create_comment" and issue is not None and comment is None:
        return "POST", "/issue/" + numeric(issue) + "/comment"
    if kind == "read_comment" and issue is not None and comment is not None:
        return "GET", "/issue/" + numeric(issue) + "/comment/" + numeric(comment)
    if kind == "comment_marker" and issue is not None and comment is not None:
        numeric(issue)
        return (
            "GET",
            "/comment/" + numeric(comment) + "/properties/" + quote("opspilot.operation", safe=""),
        )
    raise ConnectorUnavailable()


def request(
    endpoint: JiraEndpoint,
    authorization: str,
    kind: str,
    body: bytes | None,
    issue: str | None,
    comment: str | None,
) -> dict[str, Any]:
    connection = None
    stage = "validation"
    status = None
    try:
        method, path = route(kind, issue, comment)
        if kind == "find_issues" and issue != endpoint.mapping.project_id:
            raise ValueError()
        if (
            not authorization.startswith("Basic ")
            or len(authorization) > 8192
            or any(c in authorization for c in "\r\n")
            or (method == "POST") != (body is not None)
            or (body is not None and len(body) > 65536)
        ):
            raise ValueError()
        allowed = set(validate_addresses(list(endpoint.addresses)))
        deadline = time.monotonic() + 8
        stage = "dns"
        answers = {
            str(row[4][0])
            for row in socket.getaddrinfo(endpoint.host, 443, type=socket.SOCK_STREAM)
        }
        if not answers or len(answers) > 8 or not answers <= allowed:
            raise ValueError()
        pinned = sorted(answers)[0]
        context = ssl.create_default_context()

        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self) -> None:
                raw = socket.create_connection((pinned, 443), timeout=2)
                try:
                    self.sock = context.wrap_socket(raw, server_hostname=endpoint.host)
                except BaseException:
                    raw.close()
                    raise

        stage = "request"
        connection = PinnedHTTPS(endpoint.host, 443, timeout=2, context=context)
        connection.request(
            method,
            endpoint.prefix + path,
            body=body,
            headers={
                "Authorization": authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        stage = "response"
        status = response.status
        if response.status == 404 and kind in {"issue_marker", "comment_marker"}:
            return {}
        expected = 201 if method == "POST" else 200
        if (
            response.status != expected
            or response.getheader("Content-Encoding") not in (None, "identity")
            or response.getheader("Content-Type", "").split(";")[0] != "application/json"
        ):
            raise ValueError()
        raw_body = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise ValueError()
            chunk = response.read1(4096)
            if not chunk:
                break
            raw_body.extend(chunk)
            if len(raw_body) > MAX_BYTES:
                raise ValueError()
        return decode(bytes(raw_body))
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        # Fixed route names, stage and numeric status only: no URL, body or credentials.
        logger.bind(
            diagnostic_code="JIRA_" + stage.upper(),
            http_status=status,
            tool_name={
                "create_issue": "create_jira_issue",
                "create_comment": "create_jira_comment",
            }.get(kind, "get_jira_operation"),
        ).warning("jira_transport_unavailable")
        raise ConnectorUnavailable() from None
    finally:
        if connection:
            connection.close()


async def call(
    endpoint: JiraEndpoint,
    authorization: str,
    kind: str,
    *,
    body: bytes | None = None,
    issue: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    # There is deliberately one transport attempt. Unknown writes require read-back.
    return await bounded(request, endpoint, authorization, kind, body, issue, comment, budget=9)
