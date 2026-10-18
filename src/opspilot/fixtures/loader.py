from datetime import datetime, timedelta
from importlib.resources import files
from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.db.models_domain import Customer, CustomerIntegration, Incident, KnowledgeArticle
from opspilot.fixtures.models import Fixtures, MonitoringFixture

GREENSHOP_ID = "00000000-0000-0000-0000-000000000001"
GREENSHOP_INTEGRATION_ID = "00000000-0000-0000-0000-000000000101"


def load_fixtures() -> Fixtures:
    return Fixtures.model_validate_json(
        files("opspilot.fixtures").joinpath("base.json").read_text(encoding="utf-8")
    )


def load_monitoring() -> MonitoringFixture:
    return MonitoringFixture.model_validate_json(
        files("opspilot.fixtures").joinpath("scenarios.json").read_text(encoding="utf-8")
    )


def monitoring_snapshot(clock: datetime) -> dict[str, Any]:
    fixture = load_monitoring()
    return {
        "status": fixture.status,
        "credential_status": fixture.credential_status,
        "checked_at": clock,
        "latest_success_at": clock - timedelta(minutes=fixture.last_success_minutes_before_clock),
        "events": [
            {**event, "occurred_at": clock - timedelta(minutes=event["minutes_before_clock"])}
            for event in fixture.events
        ],
    }


async def seed(engine: AsyncEngine, clock: datetime) -> dict[str, int]:
    fixture = load_fixtures()
    customers = [
        {
            "id": c.id,
            "name": c.name,
            "normalized_name": c.name.casefold(),
            "metadata": {"synthetic": True},
            "created_at": clock,
        }
        for c in fixture.customers
    ]
    integrations = [{**item.model_dump(), "created_at": clock} for item in fixture.integrations]
    incidents = []
    for item in fixture.incidents:
        row = item.model_dump(exclude={"days_before_clock"})
        row.update(occurred_at=clock - timedelta(days=item.days_before_clock), created_at=clock)
        incidents.append(row)
    articles = [{**item.model_dump(), "created_at": clock} for item in fixture.articles]
    async with engine.begin() as connection:
        for model, rows in (
            (Customer, customers),
            (CustomerIntegration, integrations),
            (Incident, incidents),
            (KnowledgeArticle, articles),
        ):
            statement = insert(cast(Table, model.__table__)).values(rows)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        col.name: statement.excluded[col.name]
                        for col in model.__table__.columns
                        if col.name != "id"
                    },
                )
            )
    return {"customers": len(customers), "incidents": len(incidents), "articles": len(articles)}
