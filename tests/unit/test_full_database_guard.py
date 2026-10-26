import pytest

from opspilot.db.engine import create_engine


@pytest.mark.parametrize("database", ["opspilot", "opspilot_test", "postgres", "arbitrary"])
def test_full_engine_rejects_non_full_database_before_connect(database):
    with pytest.raises(ValueError, match="Full requires"):
        create_engine(f"postgresql+psycopg://user:secret@localhost/{database}")


@pytest.mark.parametrize("database", ["opspilot", "opspilot_test", "postgres", "arbitrary"])
async def test_checkpoint_guard_rejects_non_full_database_before_connect(database):
    from opspilot.agent.checkpoints import postgres_checkpointer
    from opspilot.config import Settings

    settings = Settings(
        mcp_service_token="a" * 64,
        checkpoint_database_url=f"postgresql+psycopg://user:secret@invalid/{database}",
    )
    with pytest.raises(ValueError, match="Full checkpoint"):
        async with postgres_checkpointer(settings):
            raise AssertionError("Non-Full checkpoint database must never be connected")
