"""Drain preceding backend fixtures before timed browser assertions; never mutate jobs."""

import asyncio
import time

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine


async def main():
    settings = Settings()
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT current_database()")) == "opspilot_full_test"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            async with engine.connect() as conn:
                pending = await conn.scalar(
                    text(
                        "SELECT count(*) FROM workflow.command_jobs "
                        "WHERE status IN ('pending','running') AND tenant_id=ANY(:tenants)"
                    ),
                    {"tenants": list(settings.recovery_tenants)},
                )
            if pending == 0:
                print("Isolated test queue drained before browser acceptance")
                return
            await asyncio.sleep(1)
        raise RuntimeError("Backend fixture queue did not drain before browser acceptance")
    finally:
        await engine.dispose()


asyncio.run(main())
