"""Compatibility entry point: API graph faults were replaced by durable queue faults in F05."""

import os

import pytest

from tests.integration.test_durable_jobs import (
    test_api_commit_loss_offline_worker_and_singleton as _queue_process_gate,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_RECOVERY_API") != "1", reason="Legacy dedicated process entry point"
)


async def test_api_hard_restart(integration_settings, admin_engine):
    await _queue_process_gate(integration_settings, admin_engine)
