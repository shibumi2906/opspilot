"""Read-only F18 database/RLS/receipt consistency gate; metadata only."""

import asyncio
import json

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine


async def main():
    engine = create_engine(Settings().database_url("migration"))
    tables = (
        "connector_configs",
        "connector_health",
        "webhook_receipts",
        "ingress_jobs",
        "observations",
        "ingress_cursors",
        "ingress_budgets",
        "audit",
    )
    try:
        async with engine.connect() as c:
            assert await c.scalar(text("SELECT current_database()")) == "opspilot_full_test"
            assert (
                await c.scalar(text("SELECT version_num FROM workflow.alembic_version"))
                == "0019_adapters"
            )
            for table in tables:
                flags = (
                    await c.execute(
                        text(
                            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                            "WHERE oid=to_regclass(:t)"
                        ),
                        {"t": "integrations." + table},
                    )
                ).one()
                assert all(flags), table
            role = (
                await c.execute(
                    text(
                        "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles "
                        "WHERE rolname='ops_ingress'"
                    )
                )
            ).one()
            assert not any(role)
            for role in ("ops_ingress", "ops_domain"):
                assert not await c.scalar(
                    text(
                        "SELECT has_table_privilege(:r,'integrations.connector_configs','UPDATE')"
                    ),
                    {"r": role},
                )
            for table in (
                "domain.tickets",
                "domain.ticket_comments",
                "domain.notifications",
                "workflow.actions",
                "workflow.approvals",
            ):
                assert not await c.scalar(
                    text(
                        "SELECT has_table_privilege('ops_ingress',:t,'SELECT,INSERT,UPDATE,DELETE')"
                    ),
                    {"t": table},
                )
            for function in (
                "integrations.ingress_config(uuid,uuid)",
                "integrations.lock_config(uuid)",
                "integrations.admit_ingress()",
                "integrations.set_ingress_password(text)",
            ):
                assert not await c.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL "
                        "aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a "
                        "WHERE p.oid=to_regprocedure(:f) AND a.grantee=0 "
                        "AND a.privilege_type='EXECUTE')"
                    ),
                    {"f": function},
                )
            assert await c.scalar(
                text(
                    "SELECT strpos(pg_get_functiondef("
                    "'integrations.admit_ingress()'::regprocedure),'100000')>0"
                )
            )
            assert not await c.scalar(
                text("""SELECT count(*) FROM integrations.webhook_receipts r
                LEFT JOIN integrations.ingress_jobs j USING(tenant_id,connector_id,event_id)
                WHERE j.event_id IS NULL OR (j.status='done')<>(r.status<>'pending')""")
            )
            assert not await c.scalar(
                text("""SELECT count(*) FROM integrations.observations o
                JOIN integrations.webhook_receipts r USING(tenant_id,connector_id,event_id)
                WHERE r.status<>'processed' OR o.source<>'synthetic' OR o.mapping_version<>1""")
            )
            assert not await c.scalar(
                text("""SELECT count(*) FROM integrations.ingress_cursors x
                WHERE x.sequence IS DISTINCT FROM (SELECT max(o.sequence)
                FROM integrations.observations o
                WHERE o.tenant_id=x.tenant_id AND o.connector_id=x.connector_id)""")
            )
            columns = (
                (
                    await c.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='integrations' AND table_name='observations'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert set(columns) == {
                "tenant_id",
                "connector_id",
                "event_id",
                "sequence",
                "status",
                "observed_at",
                "source",
                "mapping_version",
            }
            counts = {
                table: await c.scalar(text(f"SELECT count(*) FROM integrations.{table}"))
                for table in tables
            }
        result = {
            "passed": True,
            "schema": "0019_adapters",
            "force_rls_tables": list(tables),
            "ingress_privileged_role": False,
            "ingress_domain_workflow_access": False,
            "reader_config_mutation": False,
            "public_function_execute": False,
            "receipt_job_consistency": True,
            "observation_cursor_consistency": True,
            "observation_free_text_fields": False,
            "counts": counts,
        }
        print(json.dumps(result))
    finally:
        await engine.dispose()


asyncio.run(main())
