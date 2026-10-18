import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.config import Settings
from opspilot.db.engine import create_engine


@pytest.fixture
def integration_settings() -> Settings:
    if os.environ.get("APP_ENV") != "test":
        pytest.skip("Use the isolated Compose test stack (APP_ENV=test)")
    settings = Settings()
    for role in ("migration", "workflow", "domain", "checkpoint"):
        if make_url(settings.database_url(role)).database != "opspilot_test":
            pytest.fail("Integration tests require the isolated opspilot_test database")
    return settings


@pytest.fixture
async def admin_engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(integration_settings.database_url("migration"))
    try:
        yield engine
    finally:
        await engine.dispose()
