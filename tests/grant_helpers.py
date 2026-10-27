"""Trusted Core fixture for direct-domain transaction fault tests; no grant bypass."""

from typing import Any

from opspilot.auth.context import AuthError
from opspilot.config import Settings
from opspilot.mcp_server.services.tickets import create_ticket as domain_write
from opspilot.runtime.actions import payload_hash
from opspilot.security.grants import grant_scope, issue


async def create_ticket(
    engine: Any, args: Any, *, settings: Settings | None = None, **kwargs: Any
) -> dict[str, Any]:
    settings = settings or Settings()
    try:
        grant = await issue(
            settings,
            {
                "run": str(args.run_id),
                "action": str(args.action_id),
                "hash": payload_hash(args.arguments.model_dump(mode="json")),
            },
        )
    except AuthError:
        grant = None
    with grant_scope(grant):
        return await domain_write(engine, args, settings=settings, **kwargs)
