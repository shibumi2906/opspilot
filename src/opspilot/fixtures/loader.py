from datetime import datetime, timedelta
from importlib.resources import files
from typing import Any, cast
from uuid import UUID, uuid5

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.db.models_domain import (
    Customer,
    CustomerIntegration,
    Incident,
    KnowledgeArticle,
    Ticket,
)
from opspilot.db.models_workflow import Action, AgentRun, Approval
from opspilot.fixtures.models import Fixtures, MonitoringFixture
from opspilot.runtime.actions import payload_hash
from opspilot.tenancy.context import DEMO_ACTOR, DEMO_TENANT, SECOND_TENANT

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
        for tenant in (DEMO_TENANT, SECOND_TENANT):

            def mapped(value: Any, tenant: UUID = tenant) -> UUID:
                return UUID(str(value)) if tenant == DEMO_TENANT else uuid5(tenant, str(value))

            for model, source in (
                (Customer, customers),
                (CustomerIntegration, integrations),
                (Incident, incidents),
                (KnowledgeArticle, articles),
            ):
                rows = []
                for source_row in source:
                    row = dict(source_row, tenant_id=tenant)
                    row["id"] = mapped(row["id"])
                    if "customer_id" in row:
                        row["customer_id"] = mapped(row["customer_id"])
                    rows.append(row)
                statement = insert(cast(Table, model.__table__)).values(rows)
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            col.name: statement.excluded[col.name]
                            for col in model.__table__.columns
                            if col.name not in {"id", "tenant_id"}
                        },
                        where=model.__table__.c.tenant_id == tenant,
                    )
                )
            # Known, pre-existing fixture ticket: not a model-requested domain write.
            run_id, action_id, ticket_id = (
                uuid5(tenant, key) for key in ("seed-run", "seed-action", "seed-ticket")
            )
            arguments = {
                "customer_id": str(mapped(GREENSHOP_ID)),
                "title": "Synthetic baseline ticket",
                "description": "F02 fixture, no upstream write",
                "priority": "low",
                "evidence_ids": ["synthetic:f02"],
            }
            for seed_model, seed_row in (
                (
                    AgentRun,
                    dict(
                        id=run_id,
                        tenant_id=tenant,
                        actor_id=DEMO_ACTOR,
                        client_request_id=run_id,
                        request="Synthetic seed fixture",
                        request_hash="0" * 64,
                        language="en",
                        status="completed",
                        outcome="diagnosis_only",
                        mode="scripted",
                        scenario_id="healthy",
                        scenario_clock=clock,
                        thread_id=str(run_id),
                        state_schema_version=1,
                        public_snapshot={},
                        tool_results={},
                        usage={},
                    ),
                ),
                (
                    Action,
                    dict(
                        id=action_id,
                        tenant_id=tenant,
                        run_id=run_id,
                        tool_name="create_ticket",
                        arguments=arguments,
                        arguments_hash=payload_hash(arguments),
                        execution_status="succeeded",
                        execution_result={
                            "ticket_id": str(ticket_id),
                            "created_at": clock.isoformat(),
                            "replayed": False,
                        },
                        executed_at=clock,
                    ),
                ),
                (
                    Approval,
                    dict(
                        id=uuid5(tenant, "seed-approval"),
                        tenant_id=tenant,
                        action_id=action_id,
                        decision="approved",
                        decided_at=clock,
                    ),
                ),
                (
                    Ticket,
                    dict(
                        id=ticket_id,
                        tenant_id=tenant,
                        customer_id=mapped(GREENSHOP_ID),
                        originating_action_id=action_id,
                        title=arguments["title"],
                        description=arguments["description"],
                        priority="low",
                        evidence_ids=["synthetic:f02"],
                        created_at=clock,
                    ),
                ),
            ):
                await connection.execute(
                    insert(cast(Table, seed_model.__table__))
                    .values(seed_row)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
    return {
        "tenants": 2,
        "customers": len(customers) * 2,
        "incidents": len(incidents) * 2,
        "articles": len(articles) * 2,
    }
