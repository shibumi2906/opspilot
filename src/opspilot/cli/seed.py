import asyncio
import json

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.fixtures.loader import seed
from opspilot.logging import configure_logging


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url("migration"))
    try:
        print(json.dumps(await seed(engine, settings.scenario_clock)))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
