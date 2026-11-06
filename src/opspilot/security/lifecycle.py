"""Bounded operator-only lifecycle. No agent tool or automatic tenant/user deletion.

Payload erasure preserves identity/hash ledgers indefinitely (minimum policy: 365 days).
Domain business records and identity deletion require a separate reviewed workflow.
"""

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    evidence_days: int = Field(default=30, ge=1, le=3650)
    history_days: int = Field(default=90, ge=1, le=3650)
    audit_days: int = Field(default=365, ge=1, le=7300)
    batch_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def ordered(self) -> "RetentionPolicy":
        if not self.evidence_days <= self.history_days <= self.audit_days:
            raise ValueError("Retention periods must be ordered")
        return self

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


async def authorize(conn: AsyncConnection, tenant: UUID, actor: UUID) -> None:
    if await conn.scalar(text("SELECT session_user")) != "ops_migration":
        raise PermissionError("Dedicated administrative connection required")
    await conn.execute(text("SET LOCAL statement_timeout='5000'"))
    await conn.execute(text("SET LOCAL lock_timeout='2000'"))
    await conn.execute(text("SET LOCAL idle_in_transaction_session_timeout='5000'"))
    if not await conn.scalar(
        text("SELECT identity.lock_role(:a,:t,'admin')"), {"a": actor, "t": tenant}
    ):
        raise PermissionError("Active tenant administrator required")


async def record(
    conn: AsyncConnection, tenant: UUID, actor: UUID, kind: str, policy: str, count: int
) -> None:
    event_id = uuid4()
    await conn.execute(
        text("""INSERT INTO workflow.retention_jobs(id,tenant_id,actor_id,kind,policy_hash,affected)
        VALUES(:id,:t,:a,:k,:p,:n)"""),
        {"id": event_id, "t": tenant, "a": actor, "k": kind, "p": policy, "n": count},
    )
    await conn.execute(
        text("""INSERT INTO identity.security_events(id,actor_id,tenant_id,kind,details)
        VALUES(:id,:a,:t,:k,jsonb_build_object('policy_hash',CAST(:p AS text),
          'affected',CAST(:n AS integer)))"""),
        {
            "id": event_id,
            "a": actor,
            "t": tenant,
            "k": "lifecycle_" + kind,
            "p": policy,
            "n": count,
        },
    )


async def retain(
    conn: AsyncConnection,
    tenant: UUID,
    actor: UUID,
    policy: RetentionPolicy,
    *,
    apply: bool = False,
    expected_preview: str | None = None,
) -> dict[str, Any]:
    async with asyncio.timeout(5):
        return await _retain(
            conn, tenant, actor, policy, apply=apply, expected_preview=expected_preview
        )


async def _retain(
    conn: AsyncConnection,
    tenant: UUID,
    actor: UUID,
    policy: RetentionPolicy,
    *,
    apply: bool,
    expected_preview: str | None,
) -> dict[str, Any]:
    await authorize(conn, tenant, actor)
    # Serialize administrators. Lock run and lease rows before eligibility evaluation;
    # no active or pending command, approval, unknown operation, or live lease is erased.
    await conn.execute(text("SELECT pg_advisory_xact_lock(1801202617)"))
    candidates = (
        (
            await conn.execute(
                text("""
      SELECT r.id,r.request_hash,r.thread_id,r.updated_at,
       r.updated_at < clock_timestamp()-make_interval(days=>:h) AS history,
       r.updated_at < clock_timestamp()-make_interval(days=>:a) AS audit
      FROM workflow.agent_runs r
      WHERE r.tenant_id=:t AND r.status IN ('completed','cancelled','failed')
       AND r.updated_at < clock_timestamp()-make_interval(days=>:e)
       AND NOT EXISTS(SELECT 1 FROM workflow.approvals p JOIN workflow.actions x
          ON x.tenant_id=p.tenant_id AND x.id=p.action_id
          WHERE x.tenant_id=r.tenant_id AND x.run_id=r.id AND p.decision='pending')
       AND NOT EXISTS(SELECT 1 FROM workflow.actions x WHERE x.tenant_id=r.tenant_id
          AND x.run_id=r.id AND x.execution_status='unknown')
       AND NOT EXISTS(SELECT 1 FROM workflow.plan_slots s WHERE s.tenant_id=r.tenant_id
          AND s.run_id=r.id AND s.status='unknown')
       AND NOT EXISTS(SELECT 1 FROM workflow.command_jobs j WHERE j.tenant_id=r.tenant_id
          AND j.run_id=r.id AND j.status IN ('pending','running'))
       AND NOT EXISTS(SELECT 1 FROM workflow.run_execution_leases l WHERE l.tenant_id=r.tenant_id
          AND l.run_id=r.id AND l.owner IS NOT NULL AND l.lease_until>clock_timestamp())
       AND NOT EXISTS(SELECT 1 FROM workflow.deletion_tombstones d WHERE d.tenant_id=r.tenant_id
          AND d.run_id=r.id AND d.kind=CASE
           WHEN r.updated_at<clock_timestamp()-make_interval(days=>:a) THEN 'audit'
           WHEN r.updated_at<clock_timestamp()-make_interval(days=>:h) THEN 'history'
           ELSE 'evidence' END)
      ORDER BY r.id LIMIT :batch FOR UPDATE OF r
    """),
                {
                    "t": tenant,
                    "e": policy.evidence_days,
                    "h": policy.history_days,
                    "a": policy.audit_days,
                    "batch": policy.batch_size,
                },
            )
        )
        .mappings()
        .all()
    )
    preview = hashlib.sha256(
        json.dumps(
            [
                str(tenant),
                str(actor),
                policy.digest(),
                [
                    [str(r["id"]), str(r["updated_at"]), r["history"], r["audit"]]
                    for r in candidates
                ],
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if apply and expected_preview != preview:
        raise ValueError("Preview changed; preview again before applying")
    for row in candidates if apply else []:
        p = {"t": tenant, "r": row["id"], "thread": row["thread_id"]}
        await conn.execute(
            text("""INSERT INTO workflow.deletion_tombstones
          (tenant_id,run_id,action_id,kind,identity_hash)
          VALUES(:t,:r,:r,'evidence',:hash) ON CONFLICT DO NOTHING"""),
            {**p, "hash": row["request_hash"]},
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            await conn.execute(
                text(f"DELETE FROM checkpoints.{table} WHERE tenant_id=:t AND thread_id=:thread"), p
            )
        await conn.execute(
            text("""UPDATE workflow.agent_runs SET tool_results='{}',
                public_snapshot=jsonb_build_object('run_id',id,'status',status,'outcome',outcome,
                  'verification_result',jsonb_build_object('status',CASE
                    WHEN public_snapshot#>>'{verification_result,status}'
                      IN ('verified','mismatch','unavailable','unknown','not_started')
                    THEN public_snapshot#>>'{verification_result,status}' ELSE 'unknown' END))
                WHERE tenant_id=:t AND id=:r"""),
            p,
        )
        if row["history"]:
            await conn.execute(
                text("""INSERT INTO workflow.deletion_tombstones
              (tenant_id,run_id,action_id,kind,identity_hash)
              VALUES(:t,:r,:r,'history',:hash) ON CONFLICT DO NOTHING"""),
                {**p, "hash": row["request_hash"]},
            )
            await conn.execute(
                text("""INSERT INTO workflow.deletion_tombstones
              (tenant_id,run_id,action_id,kind,identity_hash,result_ref)
              SELECT x.tenant_id,x.run_id,x.id,'operation',x.revision_hash,
                COALESCE((SELECT id FROM domain.tickets WHERE originating_action_id=x.id),
                 (SELECT id FROM domain.ticket_comments WHERE originating_action_id=x.id),
                 (SELECT id FROM domain.notifications WHERE originating_action_id=x.id))
              FROM workflow.actions x WHERE tenant_id=:t AND run_id=:r
              ON CONFLICT DO NOTHING"""),
                p,
            )
            await conn.execute(
                text("""UPDATE workflow.actions SET arguments='{}',revision_document='{}',
              plan_binding=NULL,execution_result=NULL WHERE tenant_id=:t AND run_id=:r"""),
                p,
            )
            await conn.execute(
                text(
                    "UPDATE workflow.plan_slots SET template='{}',verification='{}' "
                    "WHERE tenant_id=:t AND run_id=:r"
                ),
                p,
            )
            await conn.execute(
                text(
                    "UPDATE workflow.run_plans SET document='{\"actions\":[{}]}' "
                    "WHERE tenant_id=:t AND run_id=:r"
                ),
                p,
            )
            await conn.execute(
                text("""UPDATE workflow.agent_runs SET request='',public_snapshot='{}',
              clarification=NULL,cancellation=NULL,error=NULL,usage='{}'
              WHERE tenant_id=:t AND id=:r"""),
                p,
            )
            await conn.execute(
                text(
                    "UPDATE workflow.run_streams SET projection='{}' "
                    "WHERE tenant_id=:t AND run_id=:r"
                ),
                p,
            )
            await conn.execute(
                text("""UPDATE workflow.human_commands SET payload=jsonb_build_object(
                  'erased_payload_sha256',encode(sha256(convert_to(payload::text,'UTF8')),'hex'))
                  WHERE tenant_id=:t AND run_id=:r
                  AND NOT payload ? 'erased_payload_sha256'"""),
                p,
            )
        if row["audit"]:
            # Remove dependent rows first. Stream sequence is preserved for SSE reset detection.
            for table in ("event_outbox", "run_audit", "run_events"):
                await conn.execute(
                    text(f"DELETE FROM workflow.{table} WHERE tenant_id=:t AND run_id=:r"), p
                )
            await conn.execute(
                text("""INSERT INTO workflow.deletion_tombstones
              (tenant_id,run_id,action_id,kind,identity_hash)
              VALUES(:t,:r,:r,'audit',:hash) ON CONFLICT DO NOTHING"""),
                {**p, "hash": row["request_hash"]},
            )
    await record(
        conn, tenant, actor, "compact" if apply else "preview", policy.digest(), len(candidates)
    )
    return {
        "schema_version": 1,
        "tenant_id": str(tenant),
        "preview_hash": preview,
        "applied": apply,
        "count": len(candidates),
        "policy": policy.model_dump(),
        "runs": [
            {"run_id": str(r["id"]), "history": r["history"], "audit": r["audit"]}
            for r in candidates
        ],
    }


async def export(conn: AsyncConnection, tenant: UUID, actor: UUID) -> dict[str, Any]:
    await authorize(conn, tenant, actor)
    rows = (
        (
            await conn.execute(
                text("""SELECT id,status,outcome,created_at,updated_at
      FROM workflow.agent_runs WHERE tenant_id=:t ORDER BY id LIMIT 100"""),
                {"t": tenant},
            )
        )
        .mappings()
        .all()
    )
    await record(conn, tenant, actor, "export", "metadata-v1", len(rows))
    return {
        "schema_version": 1,
        "tenant_id": str(tenant),
        "limit": 100,
        "runs": [{k: str(v) if v is not None else None for k, v in row.items()} for row in rows],
    }
