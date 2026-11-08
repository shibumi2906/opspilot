"""F22 immutable Full corpus and fail-closed release accounting.

The separate MVP corpus/runner remains unchanged. Holdout is public and inspected,
never claimed unseen. Real execution requires a separately authorized implementation.
"""

import hashlib
import json
from collections import Counter
from importlib.resources import files
from typing import Any, Literal

from pydantic import Field

from opspilot.contracts.common import StrictModel
from opspilot.evals.schema import Scenario

CATEGORIES = {
    "lookup": 10,
    "investigation": 12,
    "approval": 8,
    "security": 8,
    "infrastructure": 6,
    "ambiguity": 6,
}


class FullCase(StrictModel):
    id: str = Field(pattern=r"^F\d{2}$")
    category: Literal[
        "lookup", "investigation", "approval", "security", "infrastructure", "ambiguity"
    ]
    split: Literal["dev", "holdout"]
    tenant: Literal[0, 1]
    probe: Literal["none", "operator_denied", "cross_tenant", "anonymous", "csrf"] = "none"
    asvs_ids: list[str] = Field(min_length=1)
    scenario: Scenario


def corpus() -> list[FullCase]:
    raw = files("opspilot.evals").joinpath("full-cases.json").read_bytes()
    manifest = json.loads(files("opspilot.evals").joinpath("full-split.json").read_text())
    if hashlib.sha256(raw).hexdigest() != manifest["corpus_sha256"]:
        raise ValueError("Frozen Full corpus changed; explicit split revision required")
    cases = [FullCase.model_validate(item) for item in json.loads(raw)]
    if [c.id for c in cases] != [f"F{i:02}" for i in range(1, 51)]:
        raise ValueError("Exactly ordered F01–F50 required")
    if Counter(c.category for c in cases) != CATEGORIES:
        raise ValueError("Full category denominators changed")
    for split, count in (("dev", 30), ("holdout", 20)):
        if [c.id for c in cases if c.split == split] != manifest[split]:
            raise ValueError("Frozen split membership changed")
        if sum(c.split == split for c in cases) != count:
            raise ValueError("Invalid split denominator")
    return cases


def schedule(mode: str) -> list[tuple[FullCase, int]]:
    if mode not in {"scripted", "real"}:
        raise ValueError("Unknown eval mode")
    return [
        (c, repeat)
        for c in corpus()
        for repeat in range(1, (3 if mode == "real" and c.split == "holdout" else 1) + 1)
    ]


def accounting(results: list[dict[str, Any]], mode: str = "scripted") -> dict[str, Any]:
    expected = {(c.id, n) for c, n in schedule(mode)}
    identities = [(r["id"], r["repeat"]) for r in results]
    complete = len(identities) == len(set(identities)) and set(identities) == expected
    first = [r for r in results if r["repeat"] == 1]
    safe_metrics = ("unsupported_facts", "factual_claims", "false_success", "forbidden_calls")
    totals = {k: sum((r.get("metrics") or {}).get(k, 0) for r in results) for k in safe_metrics}
    for key in ("unauthorized_writes", "duplicates", "before_decision_delta", "ticket_delta"):
        totals[key] = sum((r.get("db") or {}).get(key, 0) for r in results)
    known_spend = sum((r.get("usage") or {}).get("known_spend_usd", 0) for r in results)
    real_execution = (
        "not_run"
        if not results
        else "incomplete"
        if not complete
        else "failed"
        if not all(r["passed"] for r in results)
        else "passed"
    )
    return {
        "planned_distinct": 50,
        "planned_runs": len(expected),
        "recorded_runs": len(results),
        "distinct_recorded": len({r["id"] for r in results}),
        "first_pass_denominator": len(first),
        "first_pass_passed": sum(r["passed"] for r in first),
        "passed": sum(r["passed"] for r in results),
        "invariants": totals,
        "db_predicate_denominator": sum(r.get("db") is not None for r in results),
        "metric_denominator": sum(r.get("metrics") is not None for r in results),
        "known_recorded_model_spend_usd": known_spend,
        "by_split": {
            s: {
                "recorded": sum(r.get("split") == s for r in results),
                "passed": sum(r["passed"] and r.get("split") == s for r in results),
            }
            for s in ("dev", "holdout")
        },
        "unknown_usage_count": sum(
            (r.get("usage") or {}).get("unknown_usage_count", 0) for r in results
        ),
        "setup_errors": sum(bool(r.get("setup_error")) for r in results),
        "complete_unique_schedule": complete,
        "scripted_gate": mode == "scripted" and complete and all(r["passed"] for r in results),
        "human_review": "pending",
        "holdout_unseen": False,
        "real_execution": "not_run" if mode == "scripted" else real_execution,
        "real_gate": "human_review_pending"
        if mode == "real" and real_execution == "passed"
        else "NOT_MET",
        "remote_ci": "not_run",
        "release_gate": "NOT_MET",
        # Catalog estimates do not prove an invoice, free-tier discount or quota eligibility.
        "actual_model_spend_usd": 0 if mode == "scripted" else None,
        "blockers": [
            "Scripted evidence does not provide real-execution acceptance"
            if mode == "scripted"
            else "Real execution alone cannot close human review or dependent gates",
            "Human claim/hypothesis review pending",
            "Remote CI not executed",
            "F20 dispatch/one-attempt/reconciliation incomplete; real Jira deferred",
            "F21 manager HIGH CVE-2026-78661 remains unresolved",
        ],
    }
