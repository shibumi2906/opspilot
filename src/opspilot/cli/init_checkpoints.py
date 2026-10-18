"""Initialize PostgreSQL checkpoint tables with the restricted checkpoint role."""

import asyncio

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.config import Settings


async def initialize(settings: Settings) -> None:
    async with postgres_checkpointer(settings):
        print("PostgreSQL checkpoint schema ready")


def main() -> None:
    asyncio.run(initialize(Settings()))


if __name__ == "__main__":
    main()
