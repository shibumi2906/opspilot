import json
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

from opspilot.auth.context import AuthError, Principal
from opspilot.auth.oidc import digest
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.security.tls import client_context


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

    async def authenticate(self, raw: str, *, touch: bool = False) -> Principal:
        if not 32 <= len(raw) <= 256:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        params = {"h": digest(raw), "idle": self.settings.session_idle_seconds}
        query = """SELECT s.*,u.issuer,u.subject FROM identity.sessions s
            JOIN identity.users u ON u.id=s.user_id WHERE s.token_hash=:h
            AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
            AND s.last_seen_at>clock_timestamp()-make_interval(secs=>:idle)
            AND u.disabled_at IS NULL"""
        async with self.engine.connect() as conn:
            row = (await conn.execute(text(query), params)).mappings().one_or_none()
        if row is None:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        if self.settings.security_profile == "hardened":
            if (
                row["auth_strength"] != self.settings.oidc_required_acr
                or not row["idp_token_ciphertext"]
            ):
                raise AuthError("REAUTHENTICATION_REQUIRED", 401)
            key = self.settings.idp_token_key
            assert key is not None
            try:
                token = (
                    Fernet(key.get_secret_value().encode())
                    .decrypt(row["idp_token_ciphertext"].encode())
                    .decode()
                )
                async with httpx.AsyncClient(
                    timeout=3,
                    trust_env=False,
                    follow_redirects=False,
                    verify=client_context(self.settings),
                ) as client:
                    response = await client.get(
                        self.settings.oidc_internal_issuer + "/protocol/openid-connect/userinfo",
                        headers={"Authorization": "Bearer " + token},
                    )
                if response.status_code != 200 or response.json().get("sub") != row["subject"]:
                    await self.revoke_sessions(row["user_id"], reason="idp_session_invalid")
                    raise AuthError("REAUTHENTICATION_REQUIRED", 401)
            except (httpx.HTTPError, InvalidToken, ValueError, KeyError, AttributeError):
                raise AuthError("IDENTITY_UNAVAILABLE", 503) from None
        async with self.engine.begin() as conn:
            current = (
                (
                    await conn.execute(
                        text("""UPDATE identity.sessions s SET
                last_seen_at=CASE WHEN :touch THEN clock_timestamp() ELSE
last_seen_at END
                WHERE s.id=:id AND s.revoked_at IS NULL AND
s.expires_at>clock_timestamp()
                AND s.last_seen_at>clock_timestamp()-make_interval(secs=>:idle)
                AND EXISTS(SELECT 1 FROM identity.users u WHERE u.id=s.user_id AND
u.disabled_at IS NULL)
                RETURNING
s.auth_time,s.expires_at,s.last_seen_at+make_interval(secs=>:idle) AS
idle_expiry"""),
                        {
                            "id": row["id"],
                            "touch": touch,
                            "idle": self.settings.session_idle_seconds,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if current is None:
            raise AuthError("AUTHENTICATION_REQUIRED", 401)
        memberships = await self.memberships(row["user_id"])
        selected = next((m for m in memberships if m["tenant_id"] == str(row["tenant_id"])), None)
        return Principal(
            row["user_id"],
            row["tenant_id"] if selected else None,
            frozenset(selected["roles"] if selected else []),
            row["id"],
            auth_time=current["auth_time"],
            expires_at=current["expires_at"],
            idle_expires_at=current["idle_expiry"],
        )

    async def audit(
        self,
        kind: str,
        user: UUID | None = None,
        tenant: UUID | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.security_events(id, actor_id, tenant_id, kind, details) "
                    "VALUES (:id, :u, :t, :k, CAST(:d AS jsonb))"
                ),
                {"id": uuid4(), "u": user, "t": tenant, "k": kind, "d": json.dumps(details or {})},
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

    async def new_session(
        self, subject: str, old: str, *, claims: dict[str, Any] | None = None
    ) -> str:
        user = uuid5(NAMESPACE_URL, self.settings.oidc_issuer + "|" + subject)
        raw = secrets.token_urlsafe(48)
        claims = claims or {}
        now = datetime.now(UTC)
        auth_time = datetime.fromtimestamp(claims.get("auth_time", now.timestamp()), UTC)
        strength = str(claims.get("acr", "single-factor"))
        cipher = None
        ttl = self.settings.session_ttl_seconds
        if self.settings.security_profile == "hardened":
            if strength != self.settings.oidc_required_acr or not claims.get("_access_token"):
                raise AuthError("REAUTHENTICATION_REQUIRED", 401)
            key = self.settings.idp_token_key
            assert key is not None
            cipher = (
                Fernet(key.get_secret_value().encode())
                .encrypt(claims["_access_token"].encode())
                .decode()
            )
            ttl = min(
                ttl,
                int(claims["_access_expires_in"]),
                max(
                    0,
                    int(
                        self.settings.oidc_max_auth_age_seconds - (now - auth_time).total_seconds()
                    ),
                ),
            )
            if ttl < 1:
                raise AuthError("REAUTHENTICATION_REQUIRED", 401)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO identity.users(id,issuer,subject) VALUES(:id,:iss,:sub) ON"
                    " CONFLICT(issuer,subject) DO NOTHING"
                ),
                {"id": user, "iss": self.settings.oidc_issuer, "sub": subject},
            )
            enabled = await conn.execute(
                text(
                    "SELECT id FROM identity.users WHERE id=:u AND disabled_at IS NULL FOR UPDATE"
                ),
                {"u": user},
            )
            if enabled.one_or_none() is None:
                raise AuthError("ACCOUNT_DISABLED", 403)
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET "
                    "revoked_at=clock_timestamp(),revocation_reason='reauthentication' "
                    "WHERE token_hash=:h"
                ),
                {"h": digest(old)},
            )
            # User-row lock serializes concurrent login and the maximum session count.
            await conn.execute(
                text("""UPDATE identity.sessions SET revoked_at=clock_timestamp(),
 revocation_reason='parallel_limit'
                WHERE id IN(SELECT id FROM identity.sessions WHERE user_id=:u AND revoked_at IS NULL
                  AND expires_at>clock_timestamp() ORDER BY created_at DESC,id OFFSET :keep)"""),
                {"u": user, "keep": self.settings.session_max_parallel - 1},
            )
            await conn.execute(
                text("""INSERT INTO
identity.sessions(id,user_id,token_hash,expires_at,tenant_id,auth_time,auth_strength,idp_sid,idp_token_ciphertext)
VALUES(:id,:u,:h,clock_timestamp()+make_interval(secs=>:ttl),NULL,:auth,:strength,:sid,:cipher)"""),
                {
                    "id": uuid4(),
                    "u": user,
                    "h": digest(raw),
                    "ttl": ttl,
                    "auth": auth_time,
                    "strength": strength,
                    "sid": claims.get("sid"),
                    "cipher": cipher,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO identity.security_events(id,actor_id,kind) VALUES(:id,:u,'login')"
                ),
                {"id": uuid4(), "u": user},
            )
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

    async def revoke_sessions(
        self, user: UUID, *, reason: str, session: UUID | None = None
    ) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity.sessions SET "
                    "revoked_at=clock_timestamp(),revocation_reason=:why WHERE user_id=:u "
                    "AND (CAST(:s AS uuid) IS NULL OR id=:s) AND revoked_at IS NULL"
                ),
                {"u": user, "s": session, "why": reason},
            )
            await conn.execute(
                text(
                    "INSERT INTO identity.security_events(id,actor_id,kind,details) "
                    "VALUES(:id,:u,'sessions_revoked',jsonb_build_object('reason',CAST(:why"
                    " AS text)))"
                ),
                {"id": uuid4(), "u": user, "why": reason},
            )

    async def sessions(self, user: UUID) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            (
                                "SELECT id,created_at,last_seen_at,expires_at,auth_time FROM "
                                "identity.sessions WHERE user_id=:u AND revoked_at IS NULL AND "
                                "expires_at>clock_timestamp() ORDER BY created_at DESC LIMIT 20"
                            )
                        ),
                        {"u": user},
                    )
                )
                .mappings()
                .all()
            )
        return [{k: (str(v) if k == "id" else v.isoformat()) for k, v in r.items()} for r in rows]

    async def consume_budget(self, key: str, limit: int, window: int = 60) -> None:
        # Committed counters include rejections; keys contain no raw IP or token.
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM identity.request_budgets WHERE expires_at<clock_timestamp()")
            )
            count = await conn.scalar(
                text("""INSERT INTO identity.request_budgets(key_hash,window_start,count,expires_at)
                VALUES(:k,floor(extract(epoch FROM
clock_timestamp())/:w)::bigint,1,clock_timestamp()+make_interval(secs=>:w*2))
                ON CONFLICT(key_hash,window_start) DO UPDATE SET
count=LEAST(identity.request_budgets.count+1,1000000) RETURNING count"""),
                {"k": digest(key), "w": window},
            )
        if count is not None and count > limit:
            raise AuthError("RATE_LIMITED", 429)
