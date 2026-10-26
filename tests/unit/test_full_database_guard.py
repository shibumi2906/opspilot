import pytest

from opspilot.db.engine import create_engine


@pytest.mark.parametrize("database", ["opspilot", "opspilot_test", "postgres", "arbitrary"])
def test_full_engine_rejects_non_full_database_before_connect(database):
    with pytest.raises(ValueError, match="Full requires"):
        create_engine(f"postgresql+psycopg://user:secret@localhost/{database}")
