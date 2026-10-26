"""Verify administratively migrated PostgreSQL checkpoint tables."""

import asyncio

from opspilot.agent.checkpoints import postgres_checkpointer
from opspilot.config import Settings
from opspilot.tenancy.context import tenant_scope


async def initialize(settings: Settings) -> None:
    async with postgres_checkpointer(settings):
        print("PostgreSQL checkpoint schema ready")


def main() -> None:
    asyncio.run(initialize(Settings()))


if __name__ == "__main__":
    with tenant_scope(Settings().local_demo_tenant):
        main()
