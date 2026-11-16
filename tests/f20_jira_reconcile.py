"""Read-only vendor reconciliation of an already-dispatched F20 operation."""

import asyncio
import json
from uuid import UUID

import httpx
from sqlalchemy import text

from opspilot.api.main import create_app
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.tenancy.context import DEMO_TENANT
from tests.auth_helpers import session_client


async def main():
    settings = Settings()
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.connect() as connection:
            operation = await connection.scalar(
                text("""
                SELECT action_id FROM integrations.jira_operations
                WHERE outcome='unknown' ORDER BY created_at DESC LIMIT 1
            """)
            )
        assert isinstance(operation, UUID), "No unknown operation to reconcile"
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=settings.app_origin
            ) as client,
        ):
            await session_client(client, settings, "operator", DEMO_TENANT)
            response = await client.post(f"/api/v2/jira/operations/{operation}/reconcile")
            print(
                json.dumps(
                    {
                        "status": response.status_code,
                        "outcome": response.json().get("outcome"),
                        "error": response.json().get("error"),
                    }
                )
            )
            assert response.status_code == 200
            assert response.json()["outcome"] == "verified"
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
