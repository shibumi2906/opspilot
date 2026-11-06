"""Read-only F12 receipt consistency, RLS and data minimization gate."""

import asyncio
import json

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.security.revisions import canonical_hash


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
                    OR (NOT EXISTS(SELECT 1 FROM workflow.deletion_tombstones m WHERE m.tenant_id=a.tenant_id AND m.run_id=a.run_id AND m.action_id=a.id AND m.kind='operation' AND m.identity_hash=a.revision_hash AND m.result_ref=d.id AND a.arguments='{{}}'::jsonb AND a.revision_document='{{}}'::jsonb AND a.execution_result IS NULL) AND (a.execution_result->>:key IS DISTINCT FROM d.id::text OR (a.execution_result-'replayed'-'created_at'-:key) <> '{{}}'::jsonb))"""),
                    {"tool": tool, "key": key},
                )
                assert bad == 0, (table, bad)
                archived = (
                    (
                        await conn.execute(
                            text(
                                f"SELECT to_jsonb(d) AS body,a.arguments_hash FROM domain.{table} d JOIN workflow.actions a ON a.tenant_id=d.tenant_id AND a.id=d.originating_action_id JOIN workflow.deletion_tombstones m ON m.tenant_id=a.tenant_id AND m.action_id=a.id AND m.run_id=a.run_id AND m.kind='operation'"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                fields = {
                    "tickets": "customer_id title description priority evidence_ids",
                    "ticket_comments": "customer_id ticket_id body evidence_ids",
                    "notifications": "customer_id recipient_id body evidence_ids",
                }[table].split()
                for receipt in archived:
                    assert (
                        canonical_hash({k: receipt["body"][k] for k in fields})
                        == receipt["arguments_hash"]
                    )
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
            for table in ("run_plans", "plan_slots"):
                flags = (
                    await conn.execute(
                        text(
                            "SELECT c.relrowsecurity,c.relforcerowsecurity FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE n.nspname='workflow' AND c.relname=:t"
                        ),
                        {"t": table},
                    )
                ).one()
                assert all(flags)
                assert not await conn.scalar(
                    text("SELECT has_table_privilege('ops_domain',:t,'SELECT')"),
                    {"t": "workflow." + table},
                )
            plans = await conn.scalar(text("SELECT count(*) FROM workflow.run_plans"))
            assert plans > 0
            assert not await conn.scalar(
                text(
                    "SELECT count(*) FROM (SELECT plan_id,count(*) n,max(wave) w,"
                    "max(verify_attempts) v FROM workflow.plan_slots GROUP BY plan_id) x "
                    "WHERE n>3 OR w>2 OR v>3"
                )
            )
            assert not await conn.scalar(
                text("""SELECT count(*) FROM workflow.plan_slots s LEFT JOIN workflow.actions a
              ON a.tenant_id=s.tenant_id AND a.id=s.action_id
              WHERE s.status='verified' AND (a.id IS NULL OR a.execution_status<>'succeeded'
              OR (NOT EXISTS(SELECT 1 FROM workflow.deletion_tombstones m WHERE m.tenant_id=a.tenant_id AND m.action_id=a.id AND m.kind='operation' AND m.identity_hash=a.revision_hash AND m.result_ref IS NOT NULL) AND (a.execution_result IS NULL OR s.verification->>'status'<>'verified')))""")
            )
            events = (
                (
                    await conn.execute(
                        text(
                            "SELECT payload FROM workflow.run_events WHERE type='plan.slot_changed'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert events
            for body in events:
                assert set(body) <= {"plan_id", "slot_id", "wave", "status", "action_id"}
            report["plan_gate"] = {
                "plans": plans,
                "bounded": True,
                "verified_receipts_consistent": True,
                "domain_direct_plan_access": False,
                "body_free_plan_events": len(events),
            }
            assert not await conn.scalar(
                text(
                    "SELECT count(*) FROM workflow.agent_runs "
                    "WHERE replan_count NOT BETWEEN 0 AND 1"
                )
            )
            replanned = await conn.scalar(
                text("SELECT count(*) FROM workflow.agent_runs WHERE replan_count=1")
            )
            assert replanned > 0
            assert not await conn.scalar(
                text(
                    "SELECT count(*) FROM workflow.action_read_budgets "
                    "WHERE attempts NOT BETWEEN 0 AND 3"
                )
            )
            assert not await conn.scalar(
                text(
                    "SELECT count(*) FROM (SELECT logical_action_id,count(*) n "
                    "FROM workflow.actions WHERE execution_status='succeeded' "
                    "GROUP BY tenant_id,logical_action_id HAVING count(*)>1) x"
                )
            )
            assert not await conn.scalar(
                text(
                    "SELECT has_table_privilege('ops_domain',"
                    "'workflow.action_read_budgets','SELECT')"
                )
            )
            flags = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                        "WHERE oid='workflow.action_read_budgets'::regclass"
                    )
                )
            ).one()
            assert all(flags)
            report["freshness_gate"] = {
                "replanned_runs": replanned,
                "run_replan_bound": 1,
                "verification_bound_per_action": 3,
                "budget_force_rls": True,
                "duplicate_succeeded_logical_intents": 0,
                "domain_direct_budget_access": False,
            }
            print(
                json.dumps(
                    {
                        "passed": True,
                        "operations": report,
                        "scope": "isolated F17; retained receipts and hash-verified tombstones; L2 NOT_MET",
                    }
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
