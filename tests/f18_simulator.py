"""A real HTTPS contract simulator, explicitly synthetic. Not Prometheus or Jira."""

import asyncio
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict

config = json.loads(Path("/run/simulator/credentials.json").read_text())
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
states: dict[str, str] = {}
hits: dict[str, int] = {}


def authorized(request: Request, token: str) -> bool:
    return hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token)


class Mode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: UUID
    mode: Literal["normal", "redirect", "oversize", "slow", "wrong_scope", "invalid", "denied"]


@app.post("/__control")
async def control(request: Request, body: Mode) -> Response:
    if not authorized(request, config["control_token"]):
        return Response(status_code=403)
    states[str(body.connector_id)] = body.mode
    return JSONResponse({"source": "synthetic", "hits": hits})


@app.get("/v1/health")
async def health(request: Request) -> Response:
    record = next((r for r in config["cases"] if authorized(request, r["credential"])), None)
    if record is None or any(
        request.headers.get("x-ops-" + k.replace("_id", "")) != record[k]
        for k in ("tenant_id", "connector_id", "customer_id", "integration_id")
    ):
        return Response(status_code=403)
    connector = record["connector_id"]
    hits[connector] = hits.get(connector, 0) + 1
    mode = states.get(connector, "normal")
    if mode == "redirect":
        return Response(
            status_code=302, headers={"Location": "https://169.254.169.254/latest/meta-data/"}
        )
    if mode == "oversize":
        return Response(b"x" * 20000, media_type="application/json")
    if mode == "slow":
        await asyncio.sleep(3)
    if mode == "invalid":
        return Response(b'{"status":"healthy","status":"unknown"}', media_type="application/json")
    if mode == "denied":
        return Response(status_code=401)
    return JSONResponse(
        {
            "status": "healthy",
            "source": "synthetic",
            "mapping_version": 1,
            "customer_id": str(uuid4()) if mode == "wrong_scope" else record["customer_id"],
            "integration_id": record["integration_id"],
            "checked_at": datetime.now(UTC).isoformat(),
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        access_log=False,
        log_level="error",
        ssl_certfile="/run/simulator/server.crt",
        ssl_keyfile="/run/simulator/server.key",
        limit_concurrency=16,
    )
