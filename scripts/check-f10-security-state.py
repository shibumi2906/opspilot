"""Read-only F10 receipt consistency, RLS and data minimization gate."""

import asyncio
import json

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine


async def main():
    engine = create_engine(Settings().database_url("migration"))
    report = {}
    try:
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT current_database()")) == "opspilot_full_test"
            for table, tool, key in [
                ("tickets", "create_ticket", "ticket_id"),
                ("ticket_comments", "add_ticket_comment", "comment_id"),
                ("notifications", "notify_manager", "notification_id"),
            ]:
                count = await conn.scalar(text(f"SELECT count(*) FROM domain.{table}"))
                assert count > 0, table
                bad = await conn.scalar(
                    text(f"""SELECT count(*) FROM domain.{table} d
                    LEFT JOIN workflow.actions a ON a.tenant_id=d.tenant_id
                    AND a.id=d.originating_action_id
                    WHERE a.id IS NULL OR a.tool_name<>:tool OR a.execution_status<>'succeeded'
                    OR a.execution_result->>:key IS DISTINCT FROM d.id::text
                    OR (a.execution_result-'replayed'-'created_at'-:key) <> '{{}}'::jsonb"""),
                    {"tool": tool, "key": key},
                )
                assert bad == 0, (table, bad)
                flags = (
                    await conn.execute(
                        text(
                            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                            "WHERE oid=to_regclass(:table)"
                        ),
                        {"table": "domain." + table},
                    )
                ).one()
                assert all(flags)
                if table != "tickets":
                    for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                        assert not await conn.scalar(
                            text("SELECT has_table_privilege('ops_domain',:table,:privilege)"),
                            {"table": "domain." + table, "privilege": privilege},
                        )
                report[tool] = {
                    "committed_objects": count,
                    "all_receipts_consistent": True,
                    "force_rls": True,
                }
            print(
                json.dumps(
                    {
                        "passed": True,
                        "operations": report,
                        "scope": "isolated local F10; full ASVS L2 remains NOT_MET",
                    }
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
