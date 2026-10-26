from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.config import Settings
from opspilot.db.models_domain import Customer, Incident, KnowledgeArticle, Ticket
from opspilot.fixtures.loader import seed
from opspilot.tenancy.context import DEMO_TENANT


async def test_seed_is_idempotent_and_preserves_nonfixture_data(
    admin_engine: AsyncEngine,
    integration_settings: Settings,
) -> None:
    clock = integration_settings.scenario_clock
    async with admin_engine.connect() as connection:
        before = list(
            (await connection.execute(select(Ticket.__table__).order_by(Ticket.id))).all()
        )
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
        assert (
            await connection.scalar(
                select(func.count()).select_from(Customer).where(Customer.tenant_id == DEMO_TENANT)
            )
            == 4
        )
        assert (
            await connection.scalar(
                select(func.count()).select_from(Incident).where(Incident.tenant_id == DEMO_TENANT)
            )
            == 10
        )
        assert (
            await connection.scalar(
                select(func.count())
                .select_from(KnowledgeArticle)
                .where(KnowledgeArticle.tenant_id == DEMO_TENANT)
            )
            == 5
        )
        assert (
            list((await connection.execute(select(Ticket.__table__).order_by(Ticket.id))).all())
            == before
        )
        await connection.rollback()
    await seed(admin_engine, clock)
    async with admin_engine.connect() as connection:
        assert (
            await connection.scalar(
                select(func.count()).select_from(Customer).where(Customer.tenant_id == DEMO_TENANT)
            )
            == 3
        )
