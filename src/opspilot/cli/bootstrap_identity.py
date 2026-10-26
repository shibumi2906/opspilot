"""Explicit local demo bootstrap; no public provisioning endpoint."""

import asyncio
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text

from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.tenancy.context import DEMO_ACTOR, DEMO_TENANT, SECOND_TENANT

SUBJECTS = {
    name: str(UUID(int=10000 + i))
    for i, name in enumerate(["demo", "operator", "approver", "auditor", "admin", "unassigned"])
}


async def bootstrap() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('ops.identity_password',:password,true)"),
                {
                    "password": settings.identity_db_password.get_secret_value()
                    if settings.identity_db_password
                    else ""
                },
            )
            await conn.execute(
                text("""DO $$ BEGIN
                IF length(current_setting('ops.identity_password'))<64 THEN
                    RAISE EXCEPTION 'Independent identity password required';
                END IF;
                EXECUTE format('ALTER ROLE ops_identity LOGIN PASSWORD %L',
                               current_setting('ops.identity_password'));
            END $$""")
            )
            if settings.allow_demo_self_approval:
                for tenant in (DEMO_TENANT, SECOND_TENANT):
                    await conn.execute(
                        text(
                            "INSERT INTO identity.tenant_memberships VALUES (:t, :u, "
                            "'approver') ON CONFLICT DO NOTHING"
                        ),
                        {"t": tenant, "u": DEMO_ACTOR},
                    )
            for name, subject in SUBJECTS.items():
                user = uuid5(NAMESPACE_URL, settings.oidc_issuer + "|" + subject)
                await conn.execute(
                    text(
                        "INSERT INTO identity.users(id, issuer, subject) VALUES (:id, "
                        ":iss, :sub) ON CONFLICT DO NOTHING"
                    ),
                    {"id": user, "iss": settings.oidc_issuer, "sub": subject},
                )
                roles = {
                    "demo": ["operator", "approver"],
                    "operator": ["operator"],
                    "approver": ["approver"],
                    "auditor": ["auditor"],
                    "admin": ["admin"],
                    "unassigned": [],
                }[name]
                for tenant in (DEMO_TENANT, SECOND_TENANT):
                    for role in roles:
                        await conn.execute(
                            text(
                                "INSERT INTO identity.tenant_memberships VALUES (:t, :u, "
                                ":r) ON CONFLICT DO NOTHING"
                            ),
                            {"t": tenant, "u": user, "r": role},
                        )
        print("Local synthetic OIDC users/memberships configured; no credentials printed")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
