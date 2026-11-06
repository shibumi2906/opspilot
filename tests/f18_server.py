"""Test-only native HTTPS application process; optional crash boundary before response."""

import asyncio
import sys
from pathlib import Path

import uvicorn

from opspilot.api.main import create_app


async def main():
    app = create_app()
    marker = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    phase = sys.argv[3] if len(sys.argv) > 3 else "after-commit"
    if marker is not None and phase == "before-commit":
        from opspilot.api import routes_ingress

        admit = routes_ingress.admit

        async def uncommitted(*args, **kwargs):
            await admit(*args, **kwargs)
            marker.write_text("receipt-and-job-uncommitted")
            await asyncio.Event().wait()

        routes_ingress.admit = uncommitted

    async def wrapped(scope, receive, send):
        async def boundary(message):
            if (
                marker is not None
                and phase == "after-commit"
                and scope.get("path", "").startswith("/ingress/v1/")
                and message["type"] == "http.response.start"
                and message["status"] == 202
            ):
                marker.write_text("committed-before-response")
                await asyncio.Event().wait()
            await send(message)

        await app(scope, receive, boundary)

    server = uvicorn.Server(
        uvicorn.Config(
            wrapped,
            host="127.0.0.1",
            port=int(sys.argv[1]),
            lifespan="on",
            log_level="error",
            access_log=False,
            ssl_certfile="/run/f18-probe/api.crt",
            ssl_keyfile="/run/f18-probe/api.key",
        )
    )
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
