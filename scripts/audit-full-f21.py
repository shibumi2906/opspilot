"""Independent read-only DB audit of the F21 lab; never accepts client 'verified' as proof."""

import asyncio
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.engine import make_url

from opspilot.cli.bootstrap_identity import SUBJECTS
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT


async def main() -> int:
    settings = Settings()
    if settings.app_env != "test" or settings.llm_mode != "scripted":
        raise ValueError("Explicit scripted test environment required")
    if make_url(settings.database_url("migration")).database != "opspilot_full_test":
        raise ValueError("Isolated test database required")
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.connect() as conn:
            result = {
                "schema": await conn.scalar(
                    text("SELECT version_num FROM workflow.alembic_version")
                ),
                "registered_connectors": await conn.scalar(
                    text("SELECT count(*) FROM integrations.connector_configs")
                ),
                "duplicate_writes": await conn.scalar(
                    text("""
SELECT count(*) FROM (SELECT tenant_id,originating_action_id FROM domain.tickets
 GROUP BY tenant_id,originating_action_id HAVING count(*)>1) x
""")
                ),
                "unapproved_writes": await conn.scalar(
                    text("""
SELECT count(*) FROM domain.tickets t JOIN workflow.actions a
 ON a.tenant_id=t.tenant_id AND a.id=t.originating_action_id
 LEFT JOIN workflow.approvals p ON p.tenant_id=a.tenant_id AND p.action_id=a.id
 WHERE a.id<>ALL(:seed_actions)
 AND (p.decision IS DISTINCT FROM 'approved' OR p.decided_at IS NULL)
"""),
                    {
                        "seed_actions": [
                            uuid5(t, "seed-action") for t in (DEMO_TENANT, SECOND_TENANT)
                        ]
                    },
                ),
                "payload_mismatches": await conn.scalar(
                    text("""
SELECT count(*) FROM domain.tickets t JOIN workflow.actions a
 ON a.tenant_id=t.tenant_id AND a.id=t.originating_action_id
 WHERE a.arguments->>'customer_id' IS DISTINCT FROM t.customer_id::text
 OR a.arguments->>'title' IS DISTINCT FROM t.title
 OR a.arguments->>'description' IS DISTINCT FROM t.description
 OR a.arguments->>'priority' IS DISTINCT FROM t.priority
 OR a.arguments->'evidence_ids' IS DISTINCT FROM t.evidence_ids
""")
                ),
                "cross_tenant_receipts": await conn.scalar(
                    text("""
SELECT count(*) FROM domain.tickets t JOIN workflow.actions a
 ON a.id=t.originating_action_id WHERE t.tenant_id<>a.tenant_id
""")
                ),
                "unknown_jobs_without_reason": await conn.scalar(
                    text("""
SELECT count(*) FROM workflow.command_jobs WHERE status='dead' AND error_code IS NULL
""")
                ),
            }
            result["run_states"] = dict(
                (
                    await conn.execute(
                        text("SELECT status,count(*) FROM workflow.agent_runs GROUP BY status")
                    )
                ).all()
            )
            result["job_states"] = dict(
                (
                    await conn.execute(
                        text("SELECT status,count(*) FROM workflow.command_jobs GROUP BY status")
                    )
                ).all()
            )
            result["worker_slot_separate_lock"] = await conn.scalar(
                text("""
SELECT position('pg_advisory_xact_lock(1801202621)' in
 pg_get_functiondef('workflow.worker_slot(uuid,boolean,uuid[])'::regprocedure))>0
""")
            )
            owner = uuid5(NAMESPACE_URL, settings.oidc_issuer + "|" + SUBJECTS["demo"])
            # Run immediately after load, before mutation-heavy negative fixtures.
            # In this fresh lab the last100 demo-owned runs are the100 paced soak runs;
            # burst/quota/pause precede them and other lab clients are not admitted.
            soak = (
                (
                    await conn.execute(
                        text("""
WITH latest AS (SELECT id,status,created_at FROM workflow.agent_runs
 WHERE actor_id=:owner ORDER BY created_at DESC LIMIT 100)
SELECT count(*) AS runs,min(created_at) AS first_created,max(created_at) AS last_created,
 (SELECT count(*) FROM workflow.command_jobs WHERE run_id IN (SELECT id FROM latest)) AS jobs,
 count(*) FILTER(WHERE status NOT IN ('completed','cancelled','failed','needs_attention')) AS active
 FROM latest
"""),
                        {"owner": owner},
                    )
                )
                .mappings()
                .one()
            )
            result["soak_window"] = {
                k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in soak.items()
            }
        result["passed"] = (
            result["schema"] == "0021_worker_admission"
            and result["worker_slot_separate_lock"]
            and soak["runs"] == 100
            and soak["jobs"] >= 200
            and soak["active"] == 0
            and all(
                result[key] == 0
                for key in (
                    "registered_connectors",
                    "duplicate_writes",
                    "unapproved_writes",
                    "payload_mismatches",
                    "cross_tenant_receipts",
                    "unknown_jobs_without_reason",
                )
            )
        )
        target = Path(os.environ.get("F21_REPORT_DIR", "/reports")) / "independent-db-audit.json"
        target.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["passed"] else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
