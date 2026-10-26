import secrets
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text

from opspilot.auth.http import csrf
from opspilot.auth.oidc import digest
from opspilot.cli.bootstrap_identity import SUBJECTS
from opspilot.db.engine import create_engine
from opspilot.tenancy.context import DEMO_TENANT


async def session_client(client, settings, name="demo", tenant=DEMO_TENANT):
    assert settings.app_env == "test"
    user = uuid5(NAMESPACE_URL, settings.oidc_issuer + "|" + SUBJECTS[name])
    raw = secrets.token_urlsafe(48)
    engine = create_engine(settings.database_url("migration"))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.sessions(id, user_id, token_hash, expires_at, "
                    "tenant_id) VALUES (:id, :u, :h, clock_timestamp()+interval '1 "
                    "hour', :t)"
                ),
                {"id": uuid4(), "u": user, "h": digest(raw), "t": tenant},
            )
        client.cookies.set("opspilot_session", raw)
        client.headers.update({"Origin": settings.app_origin, "X-CSRF-Token": csrf(settings, raw)})
        return raw, user
    finally:
        await engine.dispose()
