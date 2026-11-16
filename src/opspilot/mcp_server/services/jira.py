"""Jira effects require core authorization and a committed one-attempt receipt."""

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.auth.context import actor_id
from opspilot.config import Settings
from opspilot.contracts.actions import JiraCommentProposal, JiraIssueProposal
from opspilot.contracts.tools import JiraReceipt
from opspilot.db.models_workflow import Action
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.jira_payload import comment_payload, issue_payload
from opspilot.integrations.jira_registry import resolve
from opspilot.integrations.jira_transport import JiraEndpoint, call
from opspilot.integrations.jira_verification import comment_matches, issue_matches
from opspilot.integrations.secrets import jira_authorization
from opspilot.mcp_server.services.tickets import WriteDenied, authorize_write
from opspilot.security.grants import consume
from opspilot.tenancy.context import require_tenant
from opspilot.tenancy.session import TenantSession


async def receipt(session: TenantSession, action: UUID) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
        SELECT * FROM integrations.jira_operations
        WHERE tenant_id=identity.current_tenant() AND action_id=:action
    """),
                {"action": action},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def observe(
    endpoint: JiraEndpoint,
    authorization: str,
    args: JiraIssueProposal | JiraCommentProposal,
    operation: dict[str, Any],
    external_id: str,
    issue_id: str | None,
) -> bool:
    marker = operation["action_id"]
    payload = bytes(operation["payload"])
    if isinstance(args, JiraIssueProposal):
        document = await call(endpoint, authorization, "read_issue", issue=external_id)
        if document.get("id") != external_id:
            return False
        prop = await call(endpoint, authorization, "issue_marker", issue=external_id)
        return issue_matches(
            endpoint.mapping,
            payload,
            document,
            property_value=prop.get("value"),
            operation_id=marker,
        )
    target = await call(endpoint, authorization, "read_issue", issue=issue_id)
    if (
        target.get("id") != issue_id
        or target.get("fields", {}).get("project", {}).get("id") != endpoint.mapping.project_id
    ):
        return False
    document = await call(
        endpoint, authorization, "read_comment", issue=issue_id, comment=external_id
    )
    if document.get("id") != external_id:
        return False
    prop = await call(
        endpoint, authorization, "comment_marker", issue=issue_id, comment=external_id
    )
    return comment_matches(payload, document, property_value=prop.get("value"), operation_id=marker)


async def write(engine: AsyncEngine, args: Any, settings: Settings, tool: str) -> dict[str, Any]:
    if tool not in {"create_jira_issue", "create_jira_comment"}:
        raise WriteDenied("STATE_CONFLICT")
    async with TenantSession(engine) as session, session.begin():
        action, approval, run = await authorize_write(session, args, tool, settings)
        endpoint = await resolve(session, args.arguments)
        authorization = await jira_authorization(
            settings,
            require_tenant(),
            args.arguments.connector_id,
            endpoint.mapping.site,
            endpoint.mapping.project_id,
        )
        await consume(session, action, approval, run, settings)
        stored = await receipt(session, action.id)
        if stored:
            if (
                stored["outcome"] == "verified"
                and action.execution_status == "succeeded"
                and action.execution_result
            ):
                return {**action.execution_result, "replayed": True}
            # An existing unknown attempt never authorizes another POST.
            raise ConnectorUnavailable()
        from opspilot.security.freshness import check

        await check(session, action, settings)
        if isinstance(args.arguments, JiraIssueProposal):
            outbound = issue_payload(
                endpoint.mapping,
                action.id,
                summary=args.arguments.title,
                description=args.arguments.description,
            )
            issue_id = None
        else:
            issue_id = args.arguments.issue_id
            # The comment destination is verified independently before dispatch.
            target = await call(endpoint, authorization, "read_issue", issue=issue_id)
            if (
                target.get("id") != issue_id
                or target.get("fields", {}).get("project", {}).get("id")
                != endpoint.mapping.project_id
            ):
                raise WriteDenied("PAYLOAD_MISMATCH")
            outbound = comment_payload(action.id, body=args.arguments.body)
        await session.execute(
            text("""
            INSERT INTO integrations.jira_operations
            (action_id,run_id,connector_id,payload,payload_hash,issue_id)
            VALUES(:action,:run,:connector,:payload,:hash,:issue)
        """),
            {
                "action": action.id,
                "run": run.id,
                "connector": args.arguments.connector_id,
                "payload": outbound,
                "hash": hashlib.sha256(outbound).hexdigest(),
                "issue": issue_id,
            },
        )
        action.execution_status = "unknown"
        stored = await receipt(session, action.id)
        operation_id = action.id
    # All authorization and the one-attempt marker have committed before networking.
    response = await call(
        endpoint,
        authorization,
        "create_issue" if issue_id is None else "create_comment",
        body=outbound,
        issue=issue_id,
    )
    external_id = response.get("id")
    if not isinstance(external_id, str):
        raise ConnectorUnavailable()
    assert stored is not None
    # Save a received provider ID before additional verification calls can fail.
    # The receipt remains unknown until independent read-back succeeds.
    async with TenantSession(engine) as session, session.begin():
        await session.execute(
            text("""
            UPDATE integrations.jira_operations SET external_id=:external,
              issue_id=:issue,checked_at=clock_timestamp()
            WHERE tenant_id=identity.current_tenant() AND action_id=:action
        """),
            {"external": external_id, "issue": issue_id or external_id, "action": operation_id},
        )
    exact = await observe(endpoint, authorization, args.arguments, stored, external_id, issue_id)
    async with TenantSession(engine) as session, session.begin():
        await session.execute(
            text("""
            UPDATE integrations.jira_operations SET external_id=:external,
              issue_id=:issue, outcome=:outcome,checked_at=clock_timestamp()
            WHERE tenant_id=identity.current_tenant() AND action_id=:action
        """),
            {
                "external": external_id,
                "issue": issue_id or external_id,
                "outcome": "verified" if exact else "needs_attention",
                "action": operation_id,
            },
        )
        action = await session.get(Action, operation_id, with_for_update=True)
        assert action is not None
        result = JiraReceipt(
            operation_id=operation_id,
            external_id=external_id,
            created_at=stored["created_at"],
            replayed=False,
        ).model_dump(mode="json")
        if exact:
            action.execution_status = "succeeded"
            action.execution_result = result
    if not exact:
        raise ConnectorUnavailable()
    return result


async def observations(
    endpoint: JiraEndpoint,
    authorization: str,
    args: JiraIssueProposal | JiraCommentProposal,
    record: dict[str, Any],
    operation: UUID,
) -> tuple[list[tuple[str, bool]], bool]:
    expected_marker = json.loads(bytes(record["payload"]))["properties"][0]["value"]
    matches: list[tuple[str, bool]] = []
    complete = False
    if isinstance(args, JiraIssueProposal):
        found = await call(endpoint, authorization, "find_issues", issue=args.project_id)
        complete = found.get("isLast") is True and not found.get("nextPageToken")
        for item in found.get("issues", [])[:10]:
            identity = item.get("id")
            if not isinstance(identity, str):
                raise ConnectorUnavailable()
            prop = await call(endpoint, authorization, "issue_marker", issue=identity)
            if prop.get("value") == expected_marker:
                matches.append(
                    (identity, await observe(endpoint, authorization, args, record, identity, None))
                )
    else:
        found = await call(endpoint, authorization, "find_comments", issue=args.issue_id)
        complete = found.get("total", 11) <= 10
        for item in found.get("comments", [])[:10]:
            identity = item.get("id")
            if not isinstance(identity, str):
                raise ConnectorUnavailable()
            prop = await call(
                endpoint, authorization, "comment_marker", issue=args.issue_id, comment=identity
            )
            if prop.get("value") == expected_marker:
                matches.append(
                    (
                        identity,
                        await observe(
                            endpoint, authorization, args, record, identity, args.issue_id
                        ),
                    )
                )
    return matches, complete


async def read_operation(
    engine: AsyncEngine, operation: UUID, settings: Settings
) -> dict[str, Any] | None:
    async with TenantSession(engine) as session:
        record = await receipt(session, operation)
        if not record:
            return None
        row = (
            (
                await session.execute(
                    text("""
            SELECT a.arguments,a.tool_name,r.actor_id FROM workflow.actions a
            JOIN workflow.agent_runs r ON r.id=a.run_id AND r.tenant_id=a.tenant_id
            WHERE a.tenant_id=identity.current_tenant() AND a.id=:id
        """),
                    {"id": operation},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["actor_id"] != actor_id():
            return None
        model = (
            JiraIssueProposal if row["tool_name"] == "create_jira_issue" else JiraCommentProposal
        )
        args = model.model_validate(row["arguments"])
        endpoint = await resolve(session, args)
    authorization = await jira_authorization(
        settings, require_tenant(), args.connector_id, args.site, args.project_id
    )
    outcome = record["outcome"]
    external_id = record["external_id"]
    async with asyncio.timeout(40):
        matches, complete = await observations(endpoint, authorization, args, record, operation)
    from opspilot.auth.service_context import verified_context
    from opspilot.integrations.jira_verification import reconciliation

    observed = reconciliation([match for _, match in matches], complete=complete).value
    if external_id and matches and any(identity != external_id for identity, _ in matches):
        observed = "needs_attention"
    current_outcome = "needs_attention" if outcome == "needs_attention" else observed
    if outcome != "needs_attention":
        if observed == "needs_attention" or (outcome == "unknown" and observed == "verified"):
            outcome = observed
    if outcome == "verified" and matches:
        external_id = matches[0][0]
    context = verified_context() or {}
    # A manual reconciliation command supplies a fenced run context. Ordinary
    # evidence reads verify independently and leave the durable receipt unchanged.
    if context.get("execution_epoch") and context.get("run") == str(record["run_id"]):
        async with TenantSession(engine) as session, session.begin():
            await session.execute(
                text("""
                UPDATE integrations.jira_operations SET outcome=:outcome,
                  external_id=COALESCE(external_id,:external),
                  issue_id=COALESCE(issue_id,:issue),checked_at=clock_timestamp()
                WHERE tenant_id=identity.current_tenant() AND action_id=:action
            """),
                {
                    "outcome": outcome,
                    "external": external_id,
                    "issue": args.issue_id
                    if isinstance(args, JiraCommentProposal)
                    else external_id,
                    "action": operation,
                },
            )
    return {
        "operation_id": operation,
        "outcome": current_outcome,
        "external_id": external_id,
        "originating_action_id": operation,
        "created_at": record["created_at"],
        "arguments": row["arguments"],
    }
