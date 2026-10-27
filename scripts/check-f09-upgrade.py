"""Build a pre-F09 immutable-receipt fixture, then assert a safe F09 upgrade."""

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.security.revisions import canonical_hash

RUN = UUID("99999999-9999-4999-8999-999999999909")
ACTION = UUID("99999999-9999-4999-8999-999999999919")


async def check(phase):
    engine = create_engine(Settings().database_url("migration"))
    try:
        async with engine.begin() as conn:
            if phase == "before":
                await conn.execute(
                    text("""INSERT INTO workflow.agent_runs(id,tenant_id,actor_id,client_request_id,
                    request,request_hash,language,status,mode,scenario_id,scenario_clock,thread_id,state_schema_version,public_snapshot,tool_results,usage)
                    SELECT :r,tenant_id,actor_id,:r,'F09 upgrade pending fixture',request_hash,'en',
                    'waiting_for_approval',mode,scenario_id,scenario_clock,CAST(:r AS text),1,'{}'::jsonb,'{}'::jsonb,'{}'::jsonb
                    FROM workflow.agent_runs ORDER BY id LIMIT 1"""),
                    {"r": RUN},
                )
                await conn.execute(
                    text("""INSERT INTO workflow.actions(id,tenant_id,run_id,tool_name,arguments,arguments_hash)
                    SELECT :a,tenant_id,:r,tool_name,arguments,arguments_hash FROM workflow.actions ORDER BY id LIMIT 1"""),
                    {"a": ACTION, "r": RUN},
                )
                await conn.execute(
                    text("""INSERT INTO workflow.approvals(id,tenant_id,action_id,decision,decided_at)
                    SELECT :a,tenant_id,:a,'approved',clock_timestamp() FROM workflow.actions WHERE id=:a"""),
                    {"a": ACTION},
                )
                print("Legacy committed receipts and unexecuted approval fixture prepared")
                return
            rows = (
                (await conn.execute(text("SELECT * FROM workflow.actions ORDER BY id")))
                .mappings()
                .all()
            )
            assert rows and all(
                r["revision_hash"] == canonical_hash(r["revision_document"])
                and r["logical_action_id"]
                for r in rows
            )
            decision = await conn.scalar(
                text("SELECT decision FROM workflow.approvals WHERE action_id=:a"), {"a": ACTION}
            )
            assert decision == "revoked"
            receipts = await conn.scalar(
                text(
                    "SELECT count(*) FROM workflow.actions WHERE execution_status='succeeded' AND execution_result IS NOT NULL"
                )
            )
            tickets = await conn.scalar(text("SELECT count(*) FROM domain.tickets"))
            assert tickets == receipts == 2
            assert await conn.scalar(text("SELECT count(*) FROM workflow.execution_grants")) == 0
            print(
                json.dumps(
                    {
                        "passed": True,
                        "preserved_committed_receipts": receipts,
                        "tickets": tickets,
                        "backfilled_revisions": len(rows),
                        "legacy_unexecuted_approval": decision,
                        "new_execution_grants": 0,
                    }
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["before", "after"])
    asyncio.run(check(parser.parse_args().phase))
