from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "test"] = "local"
    workflow_database_url: SecretStr | None = None
    domain_database_url: SecretStr | None = None
    checkpoint_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    mcp_url: str = "http://mcp:8001/mcp"
    mcp_service_token: SecretStr
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_reasoning_effort: Literal["none", "low", "medium", "high"] = "low"
    agent_max_reads: int = Field(default=15, ge=1, le=15)
    agent_max_llm_attempts: int = Field(default=10, ge=1, le=10)
    agent_max_rounds: int = Field(default=6, ge=1, le=6)
    agent_max_tokens: int = Field(default=30000, ge=1, le=30000)
    agent_active_seconds: float = Field(default=120, gt=0, le=120)
    llm_mode: Literal["scripted", "real"] = "scripted"
    scenario_id: Literal["greenshop_expired", "healthy", "unknown", "timeout", "contradictory"] = (
        "greenshop_expired"
    )
    scenario_clock: datetime = datetime(2026, 10, 18, 9, tzinfo=UTC)
    demo_timezone: str = "Asia/Jerusalem"

    @field_validator("mcp_service_token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 64 or any(c not in "0123456789abcdefABCDEF" for c in token):
            raise ValueError("MCP token must contain at least 64 random hexadecimal characters")
        return value

    @field_validator("scenario_clock")
    @classmethod
    def validate_clock(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scenario clock must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator(
        "workflow_database_url",
        "domain_database_url",
        "checkpoint_database_url",
        "migration_database_url",
    )
    @classmethod
    def validate_dsn(cls, value: SecretStr | None) -> SecretStr | None:
        if (
            value is not None
            and make_url(value.get_secret_value()).drivername != "postgresql+psycopg"
        ):
            raise ValueError("Use a postgresql+psycopg URL")
        return value

    def database_url(self, role: Literal["workflow", "domain", "checkpoint", "migration"]) -> str:
        value = getattr(self, f"{role}_database_url")
        if not isinstance(value, SecretStr):
            raise ValueError(f"Missing {role} database URL")
        return value.get_secret_value()
