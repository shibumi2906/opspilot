import secrets
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import text

from opspilot.auth.context import AuthError, Principal
from opspilot.auth.oidc import digest
from opspilot.config import Settings
from opspilot.db.engine import create_engine


class IdentityStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_engine(settings.database_url("identity"))

    async def memberships(self, user: UUID) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT m.tenant_id, t.name, m.role FROM identity.tenant_memberships "
                    "m JOIN identity.tenants t ON t.id=m.tenant_id WHERE m.user_id=:u "
                    "ORDER BY m.tenant_id, m.role"
                ),
                {"u": user},
            )
            groups: dict[str, dict[str, Any]] = {}
            for row in rows.mappings():
                key = str(row["tenant_id"])
                groups.setdefault(key, {"tenant_id": key, "name": row["name"], "roles": []})[
                    "roles"
                ].append(row["role"])
            return list(groups.values())

    async def authenticate(self, raw: str) -> Principal:
        if not 32 <= len(raw) <= 256:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id, user_id, tenant_id FROM identity.sessions WHERE "
                            "token_hash=:h AND revoked_at IS NULL AND "
                            "expires_at>clock_timestamp()"
                        ),
                        {"h": digest(raw)},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        memberships = await self.memberships(row["user_id"])
        selected = next((m for m in memberships if m["tenant_id"] == str(row["tenant_id"])), None)
        return Principal(
            row["user_id"],
            row["tenant_id"] if selected else None,
            frozenset(selected["roles"] if selected else []),
            row["id"],
        )

    async def audit(self, kind: str, user: UUID | None = None, tenant: UUID | None = None) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.security_events(id, actor_id, tenant_id, kind) "
                    "VALUES (:id, :u, :t, :k)"
                ),
                {"id": uuid4(), "u": user, "t": tenant, "k": kind},
            )

    async def new_login(self) -> tuple[str, str, str, str]:
        state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM identity.login_attempts WHERE expires_at<clock_timestamp()")
            )
            await conn.execute(
                text(
                    "INSERT INTO identity.login_attempts VALUES (:s, :b, :n, :v, "
                    "clock_timestamp()+interval '5 minutes')"
                ),
                {"s": digest(state), "b": digest(binding), "n": digest(nonce), "v": verifier},
            )
        return state, binding, nonce, verifier

    async def consume_login(self, state: str, binding: str) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "DELETE FROM identity.login_attempts WHERE state_hash=:s AND "
                            "binding_hash=:b AND expires_at>clock_timestamp() RETURNING "
                            "nonce_hash, verifier"
                        ),
                        {"s": digest(state), "b": digest(binding)},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AuthError("OIDC_STATE_INVALID", 400)
        return dict(row)

    async def new_session(self, subject: str, old: str) -> str:
        user = uuid5(NAMESPACE_URL, self.settings.oidc_issuer + "|" + subject)
        raw = secrets.token_urlsafe(48)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.users(id, issuer, subject) VALUES (:id, :iss, "
                    ":sub) ON CONFLICT (issuer, subject) DO NOTHING"
                ),
                {"id": user, "iss": self.settings.oidc_issuer, "sub": subject},
            )
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET revoked_at=clock_timestamp() WHERE "
                    "token_hash=:old"
                ),
                {"old": digest(old)},
            )
            await conn.execute(
                text(
                    "INSERT INTO identity.sessions(id, user_id, token_hash, expires_at, "
                    "tenant_id) VALUES (:id, :u, :h, "
                    "clock_timestamp()+make_interval(secs=>:ttl), NULL)"
                ),
                {
                    "id": uuid4(),
                    "u": user,
                    "h": digest(raw),
                    "ttl": self.settings.session_ttl_seconds,
                },
            )
        await self.audit("login", user)
        return raw

    async def select_tenant(self, user: Principal, tenant: UUID) -> None:
        allowed = await self.memberships(user.user_id)
        if not any(m["tenant_id"] == str(tenant) for m in allowed):
            raise AuthError()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET tenant_id=:t WHERE id=:id AND "
                    "user_id=:u AND revoked_at IS NULL"
                ),
                {"t": tenant, "id": user.session_id, "u": user.user_id},
            )
        await self.audit("tenant_selected", user.user_id, tenant)

    async def logout(self, user: Principal) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("UPDATE identity.sessions SET revoked_at=clock_timestamp() WHERE id=:id"),
                {"id": user.session_id},
            )
        await self.audit("logout", user.user_id, user.tenant_id)
