from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from opspilot.config import Settings
from opspilot.fixtures.loader import GREENSHOP_ID, monitoring_snapshot


def observe(settings: Settings, customer_id: UUID, integration_id: UUID) -> dict[str, Any]:
    if settings.scenario_id == "timeout":
        raise TimeoutError("Synthetic monitoring timeout")
    snapshot = monitoring_snapshot(settings.scenario_clock)
    if str(customer_id) != GREENSHOP_ID or settings.scenario_id == "healthy":
        snapshot.update(
            status="healthy",
            credential_status="valid",
            latest_success_at=settings.scenario_clock - timedelta(minutes=1),
            events=[],
        )
    elif settings.scenario_id == "unknown":
        snapshot.update(status="unknown", credential_status="unknown", latest_success_at=None)
    elif settings.scenario_id == "contradictory":
        # Healthy status conflicts with current failed deliveries; do not hide either observation.
        snapshot.update(status="healthy", credential_status="valid")
    snapshot["events"] = [
        {k: v for k, v in event.items() if k != "minutes_before_clock"}
        | {"event_id": str(uuid5(NAMESPACE_URL, f"{integration_id}:{event['event_id']}"))}
        for event in snapshot["events"]
    ]
    return snapshot
