"""Durable wakeup delivery; DB replay is authoritative, notifications carry no state."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def publish_pending(engine: AsyncEngine) -> int:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT run_id,sequence FROM workflow.event_outbox "
                    "WHERE published_at IS NULL ORDER BY run_id,sequence LIMIT 100"
                )
            )
        ).all()
        for run_id, sequence in rows:
            await conn.execute(
                text("SELECT workflow.publish_event(:r,:s)"), {"r": run_id, "s": sequence}
            )
        return len(rows)
