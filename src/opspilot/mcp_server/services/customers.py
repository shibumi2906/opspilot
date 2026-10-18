from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from opspilot.contracts.tools import CustomerData, IntegrationSummary
from opspilot.db.models_domain import Customer, CustomerIntegration


async def get_customer(engine: AsyncEngine, customer_id: UUID) -> CustomerData | None:
    async with AsyncSession(engine) as session:
        customer = await session.get(Customer, customer_id)
        if customer is None:
            return None
        integrations = await session.scalars(
            select(CustomerIntegration)
            .where(CustomerIntegration.customer_id == customer_id)
            .order_by(CustomerIntegration.id)
        )
        return CustomerData(
            customer_id=customer.id,
            name=customer.name,
            integrations=[
                IntegrationSummary(integration_id=i.id, integration_type=i.integration_type)
                for i in integrations
            ],
        )
