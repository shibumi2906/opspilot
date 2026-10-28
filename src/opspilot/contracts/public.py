"""Versioned public exports. Internal graph dictionaries are never exported wholesale."""

from typing import Any


def pick(value: dict[str, Any], keys: str) -> dict[str, Any]:
    return {key: value[key] for key in keys.split() if key in value}


def public_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    result = pick(
        value,
        "schema_version dto_version snapshot_version actor_id run_id "
        "client_request_id request status mode model_id language "
        "outcome created_at updated_at missing_checks truncated traces",
    )
    form = value.get("clarification")
    result["clarification"] = pick(form, "id version kind expires_at") if form else None
    if form:
        result["clarification"]["options"] = [
            pick(o, "id label") for o in form.get("options", [])[:100]
        ]
        result["clarification"]["answered"] = bool(form.get("answer"))
    result["cancellation"] = (
        pick(value["cancellation"], "requested_at") if value.get("cancellation") else None
    )
    result["timeline"] = [
        pick(v, "id sequence node type status summary started_at duration_ms")
        for v in value.get("timeline", [])[:300]
    ]
    result["hypotheses"] = [
        pick(
            v,
            "hypothesis_id summary supporting_evidence_ids "
            "contradicting_evidence_ids confidence_label missing_checks",
        )
        for v in value.get("hypotheses", [])[:5]
    ]
    result["evidence"] = [
        pick(v, "evidence_id tool_name observed_at source_type source_id source_version excerpt")
        for v in value.get("evidence", [])[:100]
    ]
    # Export only the known public tool fields, including nested integration summaries.
    for item, source in zip(result["evidence"], value.get("evidence", []), strict=False):
        facts = source.get("facts", {})
        item["facts"] = pick(
            facts,
            "customer_id name status latest_success_at checked_at event_id occurred_at "
            "http_status event_type summary incident_id root_cause resolution score "
            "article_id version language title excerpt",
        )
        if "integrations" in facts:
            item["facts"]["integrations"] = [
                pick(v, "integration_id integration_type") for v in facts["integrations"][:100]
            ]
    result["usage"] = pick(
        value.get("usage", {}),
        "llm_calls read_calls input_tokens output_tokens "
        "unknown_usage_count active_ms human_wait_ms",
    )
    result["error"] = pick(value["error"], "code message") if value.get("error") else None
    report = value.get("report")
    result["report"] = (
        pick(
            report,
            "summary missing_checks action_summary ticket_id "
            "verification_status remaining_problem outcome",
        )
        if report
        else None
    )
    if report:
        result["report"]["facts"] = [
            pick(v, "statement evidence_ids") for v in report.get("facts", [])[:30]
        ]
        result["report"]["hypotheses"] = result["hypotheses"]
        result["report"]["effects"] = []
        for effect in report.get("effects", [])[:3]:
            item = pick(
                effect,
                "action_id key tool_name status approval_status "
                "verification_status wave dependencies",
            )
            item["result"] = (
                pick(effect["result"], "ticket_id comment_id notification_id created_at")
                if effect.get("result")
                else None
            )
            result["report"]["effects"].append(item)
        result["report"]["cancelled_actions"] = report.get("cancelled_actions", [])[:3]
    action = value.get("action")
    result["action"] = (
        pick(
            action,
            "action_id revision_id logical_action_id expected_version revision_hash expires_at "
            "tool_name arguments_hash approval_status execution_status wave key plan_status",
        )
        if action
        else None
    )
    if action:
        result["action"]["arguments"] = pick(
            action.get("arguments", {}),
            {
                "create_ticket": "customer_id title description priority evidence_ids",
                "add_ticket_comment": "customer_id ticket_id body evidence_ids",
                "notify_manager": "customer_id recipient_id body evidence_ids",
            }.get(action.get("tool_name"), ""),
        )
        result["action"]["result"] = (
            pick(action["result"], "ticket_id comment_id notification_id created_at replayed")
            if action.get("result")
            else None
        )
        result["action"]["verification"] = pick(action.get("verification", {}), "status")
    if value.get("plan"):
        result["plan"] = pick(value["plan"], "plan_id version hash wave")
        result["plan"]["nodes"] = [
            pick(n, "slot_id key tool_name status dependencies wave action_id")
            for n in value["plan"].get("nodes", [])[:3]
        ]
        result["actions"] = [
            public_snapshot({"action": a})["action"] for a in value.get("actions", [])[:3]
        ]
    return result
