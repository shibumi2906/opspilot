"""Trusted SQL enrollment and exact approved destination checks."""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from opspilot.contracts.actions import JiraBinding
from opspilot.integrations.egress import ConnectorUnavailable
from opspilot.integrations.jira_payload import SandboxMapping
from opspilot.integrations.jira_transport import JiraEndpoint
from opspilot.tenancy.session import TenantSession


async def resolve(session: TenantSession, arguments: JiraBinding) -> JiraEndpoint:
    row = (
        (
            await session.execute(
                text("""
        SELECT * FROM integrations.jira_bindings
        WHERE tenant_id=identity.current_tenant() AND connector_id=:id
    """),
                {"id": arguments.connector_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or not row["enabled"]
        or any(
            (
                row["customer_id"] != arguments.customer_id,
                row["version"] != arguments.mapping_version,
                row["site"] != arguments.site,
                row["project_id"] != arguments.project_id,
                row["issue_type_id"] != arguments.issue_type_id,
            )
        )
    ):
        raise ConnectorUnavailable()
    return JiraEndpoint(
        SandboxMapping(row["site"], row["project_id"], row["issue_type_id"], row["version"]),
        tuple(row["addresses"]),
        str(row["cloud_id"]) if row["cloud_id"] else None,
    )


async def for_customer(session: TenantSession, customer: UUID) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                text("""
        SELECT * FROM integrations.jira_bindings
        WHERE tenant_id=identity.current_tenant() AND customer_id=:customer AND enabled
        LIMIT 2
    """),
                {"customer": customer},
            )
        )
        .mappings()
        .all()
    )
    if len(rows) != 1:
        raise ConnectorUnavailable()
    row = rows[0]
    return {
        "connector_id": row["connector_id"],
        "mapping_version": row["version"],
        "site": row["site"],
        "project_id": row["project_id"],
        "issue_type_id": row["issue_type_id"],
    }
