"""Authenticated native-mTLS OTLP receiver for the explicit OpsPilot telemetry subset."""

import asyncio
import hashlib
import hmac
import json
import os
import ssl
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any
from uuid import UUID

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from starlette.responses import JSONResponse, Response

from opspilot.observability.journal import IntegrityError, Journal
from opspilot.observability.protocol import SERVICES, sanitize

MESSAGES: dict[str, Any] = {
    "traces": ExportTraceServiceRequest,
    "metrics": ExportMetricsServiceRequest,
    "logs": ExportLogsServiceRequest,
}


class AdmissionBusy(TimeoutError):
    """No journal operation was submitted; a trace sender may retry safely."""


def create_app(journal: Journal, tokens: dict[str, str]) -> FastAPI:
    if not tokens or any(service not in SERVICES for service in tokens.values()):
        raise ValueError("Receiver identity policy required")
    services: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = defaultdict(int)
    rates: dict[tuple[str, int], int] = {}
    admission = asyncio.Semaphore(4)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="collector-journal")

    async def bounded(function: Any, *args: Any) -> Any:
        try:
            await asyncio.wait_for(admission.acquire(), 0.2)
        except TimeoutError:
            raise AdmissionBusy from None
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(pool, lambda: function(*args))
        future.add_done_callback(lambda done: admission.release())
        return await asyncio.wait_for(asyncio.shield(future), 1.5)

    ready = journal.directory / "ready"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def monitor() -> None:
            while True:
                try:
                    await asyncio.to_thread(journal.verify)
                    ready.write_text(str(time.time()))
                except IntegrityError:
                    ready.unlink(missing_ok=True)
                    counts["integrity_failures"] += 1
                await asyncio.sleep(2)

        task = asyncio.create_task(monitor())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            ready.unlink(missing_ok=True)
            pool.shutdown(wait=True)
            journal.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> Response:
        return JSONResponse({"error": "INVALID_QUERY"}, status_code=400)

    def identity(request: Request) -> str | None:
        auth = request.headers.getlist("authorization")
        if len(auth) != 1 or not auth[0].startswith("Bearer ") or len(auth[0]) != 71:
            counts["auth_denials"] += 1
            return None
        digest = hashlib.sha256(auth[0][7:].encode()).hexdigest()
        for expected, service in tokens.items():
            if hmac.compare_digest(digest, expected):
                return service
        counts["auth_denials"] += 1
        return None

    @app.middleware("http")
    async def private_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/v1/{kind}")
    async def receive(kind: str, request: Request) -> Response:
        service = identity(request)
        if service is None:
            return Response(status_code=401)
        if (
            kind not in MESSAGES
            or request.headers.get("content-type") != "application/x-protobuf"
            or request.headers.get("content-encoding")
        ):
            return Response(status_code=415)
        minute = int(time.time() // 60)
        for key in list(rates):
            if key[1] < minute:
                del rates[key]
        key = (service, minute)
        rates[key] = rates.get(key, 0) + 1
        if rates[key] > 1000:
            counts["rate_denials"] += 1
            return Response(status_code=429)
        raw = bytearray()
        try:
            async with asyncio.timeout(2):
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > 262144:
                        return Response(status_code=413)
            message = MESSAGES[kind]()
            message.ParseFromString(bytes(raw))
            _, records = sanitize(MessageToDict(message), kind, service)
            if not records:
                return Response(status_code=400)
        except (ValueError, TypeError, KeyError, DecodeError, RecursionError, TimeoutError):
            counts["invalid_messages"] += 1
            return Response(status_code=400)
        for row in records:
            if kind == "traces":
                row["source_clock_skew"] = abs(time.time() - row["end_ns"] / 1e9) > 30
        try:
            await bounded(journal.append, records)
        except AdmissionBusy:
            counts["queue_denials"] += 1
            return Response(status_code=503, headers={"X-OpsPilot-Admission": "rejected"})
        except TimeoutError:
            counts["queue_denials"] += 1
            return Response(status_code=503)
        except IntegrityError:
            counts["integrity_failures"] += 1
            return Response(status_code=503)
        counts[kind] += len(records)
        services[service] = {
            "received_at": time.time(),
            "metrics_received_at": time.time()
            if kind == "metrics"
            else services.get(service, {}).get("metrics_received_at", 0),
            "last_kind": kind,
            "metrics": records
            if kind == "metrics"
            else services.get(service, {}).get("metrics", []),
        }
        return Response(content=b"", media_type="application/x-protobuf")

    @app.get("/internal/events")
    async def events(
        request: Request, tenant: UUID, run: UUID | None = None, actor: UUID | None = None
    ) -> Response:
        service = identity(request)
        if service != "opspilot-api" and service != "opspilot-probe":
            return Response(status_code=403)
        try:
            result = await bounded(
                journal.read,
                str(tenant),
                str(run) if run else None,
                100,
                str(actor) if actor else None,
            )
        except TimeoutError:
            counts["queue_denials"] += 1
            return JSONResponse({"available": False, "reason": "COLLECTOR_BUSY"}, status_code=503)
        except IntegrityError:
            return JSONResponse(
                {"available": False, "reason": "COLLECTOR_INTEGRITY_FAILED"}, status_code=503
            )
        result.update(
            services=services,
            counters=dict(counts),
            policy={
                "max_records": journal.limit,
                "max_database_bytes": 33554432,
                "client_clock_warning_seconds": 30,
            },
        )
        return JSONResponse(result)

    return app


def main() -> None:
    from opspilot.logging import configure_logging

    configure_logging()
    os.umask(0o077)
    directory = Path(os.environ.get("OBS_DATA", "/var/lib/opspilot-observability"))
    seals = Path(os.environ.get("OBS_SEAL", "/var/lib/opspilot-seals"))
    key = Path("/run/observability/integrity.key").read_bytes().strip()
    journal = Journal(directory, seals, key)
    tokens = json.loads(Path("/run/observability/receivers.json").read_text())
    uvicorn.run(
        create_app(journal, tokens),
        host="0.0.0.0",
        port=4318,
        access_log=False,
        log_level="error",
        log_config=None,
        proxy_headers=False,
        limit_concurrency=16,
        timeout_keep_alive=5,
        ssl_certfile="/run/observability/server.crt",
        ssl_keyfile="/run/observability/server.key",
        ssl_ca_certs="/run/observability/ca.crt",
        ssl_cert_reqs=ssl.CERT_REQUIRED,
    )


if __name__ == "__main__":
    main()
