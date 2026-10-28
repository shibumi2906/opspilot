from uuid import uuid4

import pytest

from opspilot.contracts.api import CancelRun
from opspilot.runtime.worker import process_one
from tests.integration.test_mixed_plans import choose, counts, pending


@pytest.mark.parametrize("after_first_wave", [False, True])
async def test_mixed_cancellation_preserves_all_completed_objects(
    integration_settings, admin_engine, after_first_wave
):
    service, run, value = await pending(integration_settings)
    try:
        if after_first_wave:
            for card in value["actions"]:
                await choose(service, run, card, "approve")
            await process_one(service, run)
            value = await service.snapshot(run)
            assert value["status"] == "waiting_for_approval" and value["plan"]["wave"] == 2
        await service.cancel(run, CancelRun(command_id=uuid4()))
        await process_one(service, run)
        final = await service.snapshot(run)
        assert final["status"] == "cancelled"
        statuses = {n["key"]: n["status"] for n in final["plan"]["nodes"]}
        assert statuses == {
            "ticket": "verified" if after_first_wave else "cancelled",
            "inbox": "verified" if after_first_wave else "cancelled",
            "comment": "cancelled",
        }
        assert await counts(admin_engine, run) == {
            "tickets": int(after_first_wave),
            "ticket_comments": 0,
            "notifications": int(after_first_wave),
        }
        effects = final["report"]["effects"]
        assert len(effects) == (2 if after_first_wave else 0)
        assert all(e["result"] is not None for e in effects)
    finally:
        await service.close()
