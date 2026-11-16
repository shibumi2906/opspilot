"""Durable Jira dispatch rehearsal for a local simulator.

The caller supplies an approved digest and synthetic transport. This module is
not registered with MCP and does not provide production grant authorization.
"""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from opspilot.integrations.jira_payload import SandboxMapping, approval_digest
from opspilot.integrations.jira_verification import (
    Outcome,
    comment_matches,
    issue_matches,
    reconciliation,
)


@dataclass(frozen=True)
class SimulatedOperation:
    tenant: UUID
    operation: UUID
    mapping: SandboxMapping
    payload: bytes
    issue_id: str | None = None

    def digest(self) -> str:
        if self.issue_id is not None and not (
            self.issue_id.isascii() and self.issue_id.isdigit() and len(self.issue_id) <= 20
        ):
            raise ValueError("Invalid comment target")
        envelope = f"{self.tenant}:{self.operation}:{self.issue_id or 'create'}:"
        return sha256((envelope + approval_digest(self.mapping, self.payload)).encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    site: str
    project_id: str
    issue_id: str
    record: dict[str, Any]
    marker: object


class SimulatorReceipts:
    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    tenant TEXT NOT NULL, operation TEXT NOT NULL, digest TEXT NOT NULL,
                    outcome TEXT NOT NULL, PRIMARY KEY (tenant, operation)
                )
            """)

    def dispatch(
        self, operation: SimulatedOperation, approved_digest: str, post: Callable[[], None]
    ) -> Outcome:
        digest = operation.digest()
        if approved_digest != digest:
            raise ValueError("Approval differs from exact operation")
        identity = str(operation.tenant), str(operation.operation)
        with closing(sqlite3.connect(self.path)) as db, db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?, ?, ?, ?)",
                (*identity, digest, Outcome.UNKNOWN),
            ).rowcount
            stored, outcome = db.execute(
                "SELECT digest, outcome FROM receipts WHERE tenant=? AND operation=?", identity
            ).fetchone()
            if stored != digest:
                raise ValueError("Receipt already bound to a different operation")
        # Committed before dispatch. Interruption at any later point requires read-back.
        if inserted:
            try:
                post()
            except (TimeoutError, ConnectionError):
                pass
        return Outcome(outcome)

    def reconcile(
        self, operation: SimulatedOperation, observations: list[Observation], *, complete: bool
    ) -> Outcome:
        matches = []
        expected_marker = json.loads(operation.payload)["properties"][0]["value"]
        for observed in observations:
            if observed.marker != expected_marker:
                continue
            mapping = operation.mapping
            scope = observed.site == mapping.site and observed.project_id == mapping.project_id
            if operation.issue_id is None:
                match = observed.record.get("id") == observed.issue_id and issue_matches(
                    mapping,
                    operation.payload,
                    observed.record,
                    property_value=observed.marker,
                    operation_id=operation.operation,
                )
            else:
                match = observed.issue_id == operation.issue_id and comment_matches(
                    operation.payload,
                    observed.record,
                    property_value=observed.marker,
                    operation_id=operation.operation,
                )
            matches.append(scope and match)
        outcome = reconciliation(matches, complete=complete)
        with closing(sqlite3.connect(self.path)) as db, db:
            identity = str(operation.tenant), str(operation.operation), operation.digest()
            db.execute(
                "UPDATE receipts SET outcome=? WHERE tenant=? AND operation=? AND digest=? "
                "AND (outcome=? OR (?=? AND outcome=?))",
                (
                    outcome,
                    *identity,
                    Outcome.UNKNOWN,
                    outcome,
                    Outcome.NEEDS_ATTENTION,
                    Outcome.VERIFIED,
                ),
            )
            row = db.execute(
                "SELECT outcome FROM receipts WHERE tenant=? AND operation=? AND digest=?", identity
            ).fetchone()
            if row is None:
                raise ValueError("No matching dispatch receipt")
            return Outcome(row[0])
