"""Core-only execution grants. JWTs live only in transient service transport headers."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import jwt
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from opspilot.auth.context import AuthError, actor_id
from opspilot.auth.service_context import verified_context
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from opspilot.db.models_workflow import Action, AgentRun, Approval, LogicalAction
from opspilot.runtime.fencing import current_fence
from opspilot.security.keys import FileGrantKeys
from opspilot.security.revisions import valid_revision
from opspilot.tenancy.context import require_tenant
from opspilot.tenancy.session import TenantSession

_current: ContextVar[str | None] = ContextVar("execution_grant", default=None)


@contextmanager
def grant_scope(token: str | None) -> Iterator[None]:
    saved = _current.set(token)
    try:
        yield
    finally:
        _current.reset(saved)


def verify(token: str, settings: Settings, *, now: datetime) -> dict[str, Any]:
    try:
        if len(token) > 8192:
            raise ValueError()
        header = jwt.get_unverified_header(token)
        if (
            header.get("alg") != "EdDSA"
            or header.get("typ") != "opspilot-execution+jwt"
            or header.get("crit")
        ):
            raise ValueError()
        kid = header.get("kid")
        if not isinstance(kid, str) or len(kid) > 100:
            raise ValueError()
        key = FileGrantKeys(
            settings.service_private_dir, settings.service_public_keys
        ).verification_key(kid)
        value: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            issuer="urn:opspilot:grant:" + settings.app_env,
            audience="urn:opspilot:execute:" + settings.app_env,
            options={
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "require": [
                    "iss",
                    "aud",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                    "tenant",
                    "run",
                    "revision",
                    "actor",
                    "approver",
                    "payload_hash",
                    "epoch",
                    "tool",
                    "ver",
                ],
            },
        )
        if (
            type(value["ver"]) is not int
            or value["ver"] != 1
            or value["tool"] not in {"create_ticket", "add_ticket_comment", "notify_manager"}
            or type(value["epoch"]) is not int
            or value["epoch"] < 1
        ):
            raise ValueError()
        if (
            any(type(value[k]) is not int for k in ["iat", "nbf", "exp"])
            or not 0 < value["exp"] - value["iat"] <= 60
        ):
            raise ValueError()
        if not value["iat"] <= now.timestamp() < value["exp"] or value["nbf"] != value["iat"]:
            raise ValueError()
        for k in ["jti", "tenant", "run", "revision", "actor", "approver"]:
            UUID(value[k])
        return {**value, "kid": kid}
    except (jwt.PyJWTError, ValueError, KeyError, TypeError, OSError):
        raise AuthError("GRANT_INVALID") from None


async def issue(settings: Settings, operation: dict[str, str]) -> str:
    fence = current_fence()
    if fence is None or str(fence.run) != operation["run"]:
        raise AuthError("GRANT_REQUIRED")
    engine = create_engine(settings.database_url("workflow"))
    try:
        async with TenantSession(engine) as session, session.begin():
            await session.execute(text("SELECT workflow.check_not_cancelled(:r)"), {"r": fence.run})
            action = await session.get(Action, UUID(operation["action"]))
            if (
                action is None
                or action.run_id != fence.run
                or action.tool_name != operation.get("tool", "create_ticket")
                or action.arguments_hash != operation["hash"]
            ):
                raise AuthError("GRANT_INVALID")
            logical = await session.get(LogicalAction, action.logical_action_id)
            approval = await session.scalar(
                select(Approval).where(Approval.action_id == action.id).with_for_update()
            )
            run = await session.get(AgentRun, fence.run)
            now = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            if (
                run is None
                or run.actor_id != actor_id()
                or logical is None
                or logical.current_revision_id != action.id
                or action.superseded_at
                or approval is None
                or approval.decision != "approved"
                or approval.decided_by is None
                or approval.decided_at is None
                or now >= approval.expires_at
                or now >= action.expires_at
                or not valid_revision(action)
            ):
                raise AuthError("APPROVAL_REQUIRED")
            for user, role in [(run.actor_id, "operator"), (approval.decided_by, "approver")]:
                if not await session.scalar(
                    text("SELECT identity.lock_role(:u,:t,:role)"),
                    {"u": user, "t": run.tenant_id, "role": role},
                ):
                    raise AuthError("APPROVAL_REQUIRED")
            if run.actor_id == approval.decided_by and (
                not settings.allow_demo_self_approval or not approval.self_approval_exception
            ):
                raise AuthError("APPROVAL_REQUIRED")
            ref, key = await asyncio.to_thread(
                FileGrantKeys(
                    settings.service_private_dir, settings.service_public_keys
                ).signing_key,
                settings.grant_active_kid,
            )
            iat = int(now.timestamp())
            exp = min(
                iat + settings.grant_ttl_seconds,
                int(approval.expires_at.timestamp()),
                int(action.expires_at.timestamp()),
            )
            if exp <= iat:
                raise AuthError("APPROVAL_EXPIRED", 410)
            claims = {
                "ver": 1,
                "iss": "urn:opspilot:grant:" + settings.app_env,
                "aud": "urn:opspilot:execute:" + settings.app_env,
                "iat": iat,
                "nbf": iat,
                "exp": exp,
                "jti": str(uuid4()),
                "tenant": str(run.tenant_id),
                "run": str(run.id),
                "revision": str(action.id),
                "tool": action.tool_name,
                "actor": str(run.actor_id),
                "approver": str(approval.decided_by),
                "payload_hash": action.revision_hash,
                "epoch": fence.epoch,
            }
            await session.execute(
                text("""INSERT INTO workflow.execution_grants
(tenant_id,jti,run_id,revision_id,actor_id,approver_id,revision_hash,kid,epoch,issued_at,expires_at)
VALUES(:tenant,:jti,:run,:revision,:actor,:approver,:payload_hash,:kid,:epoch,to_timestamp(:iat),to_timestamp(:exp))"""),
                {**claims, "kid": ref.kid},
            )
            return jwt.encode(
                claims,
                key,
                algorithm="EdDSA",
                headers={"kid": ref.kid, "typ": "opspilot-execution+jwt"},
            )
    except DBAPIError as exc:
        if (
            getattr(exc.orig, "sqlstate", None) == "P0001"
            and str(exc.orig).splitlines()[0] == "RUN_CANCELLED"
        ):
            from opspilot.runtime.human_commands import RunCancelled

            raise RunCancelled() from None
        raise
    finally:
        await engine.dispose()


async def consume(
    session: TenantSession, action: Action, approval: Approval, run: AgentRun, settings: Settings
) -> None:
    token = _current.get()
    if token is None:
        raise AuthError("GRANT_REQUIRED")
    first_now = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(first_now, datetime)
    claims = verify(token, settings, now=first_now)
    context = verified_context() or {}
    fence = current_fence()
    epoch = fence.epoch if fence else context.get("execution_epoch")
    expected = {
        "tenant": str(require_tenant()),
        "run": str(run.id),
        "revision": str(action.id),
        "actor": str(run.actor_id),
        "approver": str(approval.decided_by),
        "payload_hash": action.revision_hash,
        "epoch": epoch,
        "tool": action.tool_name,
    }
    if any(claims[k] != v for k, v in expected.items()):
        raise AuthError("GRANT_INVALID")
    row = (
        (
            await session.execute(
                text("""SELECT * FROM workflow.execution_grants
         WHERE tenant_id=identity.current_tenant() AND jti=:j FOR UPDATE"""),
                {"j": UUID(claims["jti"])},
            )
        )
        .mappings()
        .one_or_none()
    )
    now = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    if (
        now >= approval.expires_at
        or now >= action.expires_at
        or row is None
        or row["revoked_at"]
        or now >= row["expires_at"]
        or row["run_id"] != run.id
        or int(row["issued_at"].timestamp()) != claims["iat"]
        or row["revision_id"] != action.id
        or row["revision_hash"] != action.revision_hash
        or row["epoch"] != epoch
        or row["kid"] != claims["kid"]
        or row["actor_id"] != run.actor_id
        or row["approver_id"] != approval.decided_by
        or int(row["expires_at"].timestamp()) != claims["exp"]
    ):
        raise AuthError("GRANT_INVALID")
    if row["consumed_at"] and action.execution_status != "succeeded":
        raise AuthError("GRANT_REPLAY")
    if not row["consumed_at"]:
        await session.execute(
            text(
                "UPDATE workflow.execution_grants SET consumed_at=clock_timestamp() WHERE "
                "jti=:j AND tenant_id=identity.current_tenant()"
            ),
            {"j": UUID(claims["jti"])},
        )
