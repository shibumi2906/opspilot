from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.config import Settings
from opspilot.db.models_domain import Customer, Incident, KnowledgeArticle, Ticket
from opspilot.fixtures.loader import seed


async def test_seed_is_idempotent_and_preserves_nonfixture_data(
    admin_engine: AsyncEngine,
    integration_settings: Settings,
) -> None:
    clock = integration_settings.scenario_clock
    await seed(admin_engine, clock)
    async with admin_engine.begin() as connection:
        # This transaction rolls back even if an assertion fails: no fixture cleanup dependency.
        await connection.execute(
            Customer.__table__.insert().values(
                id=UUID(int=999),
                name="Operator-created",
                normalized_name="operator-created",
                metadata={},
                created_at=clock,
            )
        )
        # Run seed in its own transaction; it must leave this unrelated customer untouched.
        await seed(admin_engine, clock)
        assert await connection.scalar(select(func.count()).select_from(Customer)) == 4
        assert await connection.scalar(select(func.count()).select_from(Incident)) == 10
        assert await connection.scalar(select(func.count()).select_from(KnowledgeArticle)) == 5
        assert await connection.scalar(select(func.count()).select_from(Ticket)) == 0
        await connection.rollback()
    await seed(admin_engine, clock)
    async with admin_engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Customer)) == 3
