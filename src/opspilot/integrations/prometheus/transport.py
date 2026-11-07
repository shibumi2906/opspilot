"""Fixed scoped GET templates, all-answer address pinning, verified TLS and bounded replies."""

import http.client
import json
import math
import socket
import ssl
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from opspilot.integrations.egress import ConnectorUnavailable, origin
from opspilot.integrations.executor import bounded
from opspilot.integrations.prometheus.registry import Registration

METRIC = "opspilot_integration_health"
MAX_BYTES = 65536


def selector(reg: Registration) -> str:
    return (
        METRIC
        + '{job="opspilot",tenant_id="'
        + str(reg.tenant_id)
        + '",customer_id="'
        + str(reg.customer_id)
        + '",integration_id="'
        + str(reg.integration_id)
        + '",opspilot_target=~"'
        + "|".join(reg.targets)
        + '"}'
    )


def expression(reg: Registration) -> str:
    selected = selector(reg)
    # Values and original sample timestamps share one bounded engine evaluation.
    return (
        f'label_replace({selected},"opspilot_measure","health","job","opspilot") or '
        f'label_replace(timestamp({selected}),"opspilot_measure","sample_time","job","opspilot")'
    )


def decode(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise ValueError()

    result = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError()
    return result


def _request(
    reg: Registration, authorization: str, path: str, params: dict[str, str], deadline: float
) -> dict[str, Any]:
    connection = None
    try:
        host, port = origin(reg.origin)
        if path not in {"/api/v1/query", "/api/v1/query_range", "/api/v1/status/buildinfo"}:
            raise ValueError()
        query = expression(reg)
        if path != "/api/v1/status/buildinfo":
            if (
                params.get("query") != query
                or params.get("timeout") != "500ms"
                or params.get("limit") != "17"
            ):
                raise ValueError()
            if set(params) != (
                {"query", "time", "timeout", "limit"}
                if path == "/api/v1/query"
                else {"query", "start", "end", "step", "timeout", "limit"}
            ):
                raise ValueError()
        elif params:
            raise ValueError()
        answers = {
            str(row[4][0]) for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
        if not answers or len(answers) > 8 or not answers.issubset(reg.addresses):
            raise ValueError()
        pinned = sorted(answers)[0]
        if time.monotonic() >= deadline:
            raise ValueError()
        context = ssl.create_default_context(cafile=reg.ca_file)

        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self) -> None:
                raw = socket.create_connection((pinned, port), timeout=0.5)
                try:
                    self.sock = context.wrap_socket(raw, server_hostname=host)
                except BaseException:
                    raw.close()
                    raise

        connection = PinnedHTTPS(host, port, timeout=0.5, context=context)
        headers = {
            "Authorization": authorization,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        if reg.tenant_header:
            headers["X-Scope-OrgID"] = str(reg.tenant_header)
        connection.request(
            "GET", path + ("?" + urlencode(params) if params else ""), headers=headers
        )
        response = connection.getresponse()
        if (
            response.status != 200
            or response.getheader("Content-Encoding") not in {None, "identity"}
            or response.getheader("Content-Type", "").split(";")[0] != "application/json"
        ):
            raise ValueError()
        raw_body = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise ValueError()
            # One socket read per iteration: a drip-fed body cannot keep a read(n)
            # filling its buffer beyond the absolute request deadline.
            chunk = response.read1(4096)
            if not chunk:
                break
            raw_body.extend(chunk)
            if len(raw_body) > MAX_BYTES:
                raise ValueError()
        body = decode(bytes(raw_body))
        if body.get("status") != "success" or body.get("warnings") or body.get("infos"):
            raise ValueError()
        return body
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        raise ConnectorUnavailable() from None
    finally:
        if connection:
            connection.close()


def _query(
    reg: Registration, authorization: str, now: float, window: tuple[datetime, datetime] | None
) -> tuple[dict[str, Any], int]:
    path = "/api/v1/query"
    params = {"time": f"{now:.3f}", "timeout": "500ms", "limit": "17"}
    step = 0
    if window:
        start, end = (value.timestamp() for value in window)
        if not 0 < end - start <= 7 * 86400 or end > now + 30:
            raise ConnectorUnavailable()
        step = max(15, math.ceil((end - start) / 120 / 15) * 15)
        params = {
            "start": f"{start:.3f}",
            "end": f"{end - 0.001:.3f}",
            "step": str(step),
            "timeout": "500ms",
            "limit": "17",
        }
        path = "/api/v1/query_range"
    deadline = time.monotonic() + 2
    body = _request(reg, authorization, path, {**params, "query": expression(reg)}, deadline)
    return body, step


async def query(
    reg: Registration, authorization: str, now: float, window: tuple[datetime, datetime] | None
) -> tuple[dict[str, Any], int]:
    try:
        return await bounded(_query, reg, authorization, now, window, budget=2.5)
    except TimeoutError:
        raise ConnectorUnavailable() from None


async def build_info(reg: Registration, authorization: str) -> dict[str, Any]:
    try:
        return await bounded(
            _request,
            reg,
            authorization,
            "/api/v1/status/buildinfo",
            {},
            time.monotonic() + 1,
            budget=1.5,
        )
    except TimeoutError:
        raise ConnectorUnavailable() from None
