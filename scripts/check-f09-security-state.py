"""Read-only assertions against the real F09 release DB after integration tests."""
import asyncio
import json
from sqlalchemy import text
from opspilot.config import Settings
from opspilot.db.engine import create_engine

async def main():
    engine = create_engine(Settings().database_url("migration"))
    try:
        async with engine.connect() as conn:
            events = (await conn.execute(text("SELECT type,payload FROM workflow.run_events WHERE type LIKE 'grant.%' OR type='revision.current_changed'"))).mappings().all()
            kinds = {row["type"] for row in events}
            assert {"grant.issued", "grant.consumed", "revision.current_changed"} <= kinds
            for row in events:
                allowed = {"logical_action_id", "revision_id", "version"} if row["type"] == "revision.current_changed" else {"revision_id", "jti", "kid", "epoch"}
                assert set(row["payload"]) <= allowed
                assert "eyJ" not in json.dumps(row["payload"])
            for role,table,privilege in [("ops_domain","workflow.approvals","UPDATE"),("ops_domain","workflow.execution_grants","INSERT"),("ops_workflow","workflow.run_audit","DELETE")]:
                assert not await conn.scalar(text("SELECT has_table_privilege(:r,:t,:p)"), {"r":role,"t":table,"p":privilege})
            assert await conn.scalar(text("SELECT has_column_privilege('ops_domain','workflow.execution_grants','consumed_at','UPDATE')"))
            assert not await conn.scalar(text("SELECT has_column_privilege('ops_domain','workflow.execution_grants','revoked_at','UPDATE')"))
            print(json.dumps({"passed": True, "security_events": len(events), "event_kinds": sorted(kinds), "payloads": "IDs/version/hash/key metadata only; no JWT", "least_privilege": "domain cannot approve/issue/revoke; audit delete denied"}))
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
