"""Explicit local administrative preview/apply/export; never registered as an agent tool."""

import argparse
import asyncio
import json
from uuid import UUID

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.security.lifecycle import RetentionPolicy, export, retain
from opspilot.tenancy.context import tenant_scope


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["preview", "compact", "export"])
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--actor", type=UUID, required=True)
    parser.add_argument("--preview-hash")
    parser.add_argument("--evidence-days", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=90)
    parser.add_argument("--audit-days", type=int, default=365)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()
    policy = RetentionPolicy(
        evidence_days=args.evidence_days,
        history_days=args.history_days,
        audit_days=args.audit_days,
        batch_size=args.batch_size,
    )
    engine = create_engine(Settings().database_url("migration"))
    try:
        with tenant_scope(args.tenant):
            async with engine.begin() as conn:
                result = (
                    await export(conn, args.tenant, args.actor)
                    if args.operation == "export"
                    else await retain(
                        conn,
                        args.tenant,
                        args.actor,
                        policy,
                        apply=args.operation == "compact",
                        expected_preview=args.preview_hash,
                    )
                )
        print(json.dumps(result, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
