"""Test-only process pause after observation mutation and before transaction commit."""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.integrations import service
from opspilot.tenancy.context import tenant_scope


async def main():
    settings = Settings()
    engine = create_engine(settings.database_url("ingress"))
    audit = service.audit

    async def boundary(c, connector, kind, event=None):
        await audit(c, connector, kind, event)
        if str(event) == sys.argv[2]:
            await asyncio.to_thread(Path(sys.argv[1]).write_text, "observation-uncommitted")
            await asyncio.Event().wait()

    service.audit = boundary
    try:
        with tenant_scope(UUID(sys.argv[3])):
            while await service.process_one(engine):
                pass
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
