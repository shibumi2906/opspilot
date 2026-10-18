import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.config import Settings
from opspilot.db.engine import create_engine


@pytest.mark.parametrize(
    "role, forbidden_sql",
    [
        ("workflow", "SELECT * FROM domain.customers"),
        ("domain", "UPDATE workflow.approvals SET decision = 'approved'"),
        ("domain", "UPDATE workflow.actions SET arguments = '{}'::jsonb"),
        ("domain", "DELETE FROM domain.customers"),
        ("checkpoint", "SELECT * FROM domain.customers"),
    ],
)
async def test_role_boundaries(
    integration_settings: Settings, role: str, forbidden_sql: str
) -> None:
    engine = create_engine(integration_settings.database_url(role))
    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(text(forbidden_sql))
    finally:
        await engine.dispose()


async def test_checkpoint_schema_search_path(integration_settings: Settings) -> None:
    engine = create_engine(integration_settings.database_url("checkpoint"))
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT current_schema()")) == "checkpoints"
            assert (
                await connection.scalar(
                    text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
                )
                is False
            )
    finally:
        await engine.dispose()
