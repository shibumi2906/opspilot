"""Operator-only role provisioning. No raw SQL errors or password are printed."""

import asyncio

from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.config import Settings
from opspilot.db.engine import create_engine


async def main() -> None:
    settings = Settings()
    incoming = make_url(settings.database_url("ingress"))
    migration = make_url(settings.database_url("migration"))
    if incoming.database != migration.database or not incoming.password:
        raise ValueError("Dedicated Full ingress role and matching database required")
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.begin() as c:
            await c.execute(
                text("SELECT integrations.set_ingress_password(:p)"), {"p": incoming.password}
            )
    except Exception:
        raise RuntimeError("Ingress role provisioning failed") from None
    finally:
        await engine.dispose()
    print("Independent observation-only ingress role provisioned")


if __name__ == "__main__":
    asyncio.run(main())
