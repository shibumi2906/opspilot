"""Observation processor configuration without business, MCP or manager credentials."""

from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT


class IngressWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "test", "production"] = "local"
    security_profile: Literal["development", "hardened"] = "development"
    ingress_database_url: SecretStr | None = None
    ingress_database_url_file: str | None = None
    recovery_tenants: tuple[UUID, ...] = Field(
        default=(DEMO_TENANT, SECOND_TENANT), min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def dedicated_role(self) -> Self:
        if self.ingress_database_url_file:
            path = Path(self.ingress_database_url_file)
            if (
                self.ingress_database_url is not None
                or not path.is_absolute()
                or not path.is_file()
                or path.stat().st_size > 8192
            ):
                raise ValueError("Unambiguous private ingress DSN file required")
            self.ingress_database_url = SecretStr(path.read_text().strip())
        if self.ingress_database_url is None:
            raise ValueError("Dedicated ingress DSN required")
        url = make_url(self.ingress_database_url.get_secret_value())
        if (
            url.drivername != "postgresql+psycopg"
            or url.username != "ops_ingress"
            or url.database not in {"opspilot_full", "opspilot_full_test"}
            or (self.app_env == "production" and self.security_profile != "hardened")
            or (self.security_profile == "hardened" and url.query.get("sslmode") != "verify-full")
        ):
            raise ValueError("Dedicated Full ingress role and transport policy required")
        return self

    def database_url(self) -> str:
        assert self.ingress_database_url is not None
        return self.ingress_database_url.get_secret_value()
