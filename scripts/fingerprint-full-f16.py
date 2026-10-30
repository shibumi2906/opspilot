"""Metadata-only logical fingerprints, used with the Full services quiesced."""

import asyncio
import json

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine

TABLES = (
    "domain.customers",
    "domain.customer_integrations",
    "domain.incidents",
    "domain.knowledge_articles",
    "domain.tickets",
    "domain.ticket_comments",
    "domain.notifications",
    "domain.connector_controls",
    "workflow.actions",
    "workflow.agent_runs",
    "workflow.approvals",
    "workflow.command_jobs",
)


async def main():
    engine = create_engine(Settings().database_url("migration"))
    try:
        result = {}
        async with engine.connect() as c:
            result["schema"] = await c.scalar(
                text("SELECT version_num FROM workflow.alembic_version")
            )
            for table in TABLES:
                projection = "to_jsonb(t)"
                if table == "workflow.command_jobs":
                    projection += " - 'traceparent' - 'first_claimed_at' - 'claimed_at'"
                value = await c.execute(
                    text(
                        "SELECT count(*) AS count,encode(sha256(convert_to(COALESCE("
                        f"string_agg(({projection})::text,'' ORDER BY ({projection})::text),''),"
                        "'UTF8')),'hex') AS sha256 "
                        f"FROM {table} t"
                    )
                )
                result[table] = dict(value.mappings().one())
        print(json.dumps(result, sort_keys=True))
    finally:
        await engine.dispose()


asyncio.run(main())
