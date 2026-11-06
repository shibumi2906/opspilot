from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from opspilot.tenancy.context import DEMO_TENANT, SECOND_TENANT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    redis_url: SecretStr | None = None
    redis_password: SecretStr | None = None
    cache_signing_key: SecretStr | None = None
    redis_password_file: str | None = None
    cache_signing_key_file: str | None = None

    @model_validator(mode="after")
    def validate_cache(self) -> Self:
        for target in ("redis_password", "cache_signing_key"):
            file = getattr(self, target + "_file", None)
            if file:
                path = Path(file)
                if not path.is_absolute() or not path.is_file() or path.stat().st_size > 128:
                    raise ValueError("Private Redis/cache secret file unavailable")
                if getattr(self, target):
                    raise ValueError("Ambiguous cache secret configuration")
                setattr(self, target, SecretStr(path.read_text().strip()))
        if self.redis_url:
            parsed = urlsplit(self.redis_url.get_secret_value())
            if (
                parsed.scheme not in {"redis", "rediss"}
                or not parsed.hostname
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Explicit Redis origin without URL credentials/options required")
            if self.security_profile == "hardened" and (
                parsed.scheme != "rediss" or not self.tls_ca_file
            ):
                raise ValueError("Hardened Redis requires verified native TLS")
            if any(
                not getattr(self, key) or len(getattr(self, key).get_secret_value()) < 64
                for key in ("redis_password", "cache_signing_key")
            ):
                raise ValueError(
                    "Independent strong Redis password and cache integrity key required"
                )
        return self

    otel_endpoint: str | None = None
    telemetry_ca_file: str | None = None
    telemetry_cert_file: str | None = None
    telemetry_key_file: str | None = None
    telemetry_token_file: str | None = None

    @model_validator(mode="after")
    def verified_telemetry(self) -> Self:
        if self.otel_endpoint:
            value = urlsplit(self.otel_endpoint)
            if (
                value.scheme != "https"
                or not value.hostname
                or value.username
                or value.password
                or value.query
                or value.fragment
                or value.path != "/v1/traces"
            ):
                raise ValueError("Telemetry requires an explicit trusted HTTPS traces origin")
            for filename in (
                self.telemetry_ca_file,
                self.telemetry_cert_file,
                self.telemetry_key_file,
                self.telemetry_token_file,
            ):
                if not filename or not Path(filename).is_absolute() or not Path(filename).is_file():
                    raise ValueError("Independent telemetry TLS and service credentials required")
            assert self.telemetry_token_file is not None
            token = Path(self.telemetry_token_file).read_text().strip()
            if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
                raise ValueError("Strong telemetry service credential required")
        return self

    jaeger_query_url: str = "http://jaeger:16686"
    jaeger_url: str | None = None

    worker_lease_seconds: float = Field(default=30, gt=0)
    worker_heartbeat_seconds: float = Field(default=10, gt=0)

    @model_validator(mode="after")
    def validate_worker_timing(self) -> Self:
        if self.worker_heartbeat_seconds >= self.worker_lease_seconds:
            raise ValueError("Worker heartbeat must be shorter than the lease")
        return self

    recovery_tenants: tuple[UUID, ...] = (DEMO_TENANT, SECOND_TENANT)

    service_private_dir: str = "/run/service-private"
    service_public_keys: str = "/run/service-public/keys.json"
    service_active_kid: str = "current"
    secret_manager_url: str | None = None
    secret_manager_ca_file: str | None = None
    secret_manager_token_file: str | None = None

    @model_validator(mode="after")
    def manager_configuration(self) -> Self:
        values = (
            self.secret_manager_url,
            self.secret_manager_ca_file,
            self.secret_manager_token_file,
        )
        if any(values) and not all(values):
            raise ValueError("Complete secret manager configuration required")
        if self.secret_manager_url:
            from opspilot.security.manager import BaoGrantKeys

            BaoGrantKeys(
                self.secret_manager_url,
                self.secret_manager_ca_file or "",
                self.secret_manager_token_file or "",
            )
        return self

    grant_active_kid: str = Field(default="grant-current", pattern=r"^grant-(current|next)$")
    approval_ttl_seconds: int = Field(default=900, ge=1, le=86400)
    grant_ttl_seconds: int = Field(default=60, ge=1, le=60)

    identity_database_url: SecretStr | None = None
    identity_db_password: SecretStr | None = None
    session_signing_key: SecretStr = SecretStr("")
    security_role: Literal["api", "worker", "mcp", "admin", "audit"] = "api"
    tls_ca_file: str | None = None
    tls_cert_file: str | None = None
    tls_key_file: str | None = None
    security_profile: Literal["development", "hardened"] = "development"
    session_idle_seconds: int = Field(default=900, ge=60, le=3600)
    session_max_parallel: int = Field(default=3, ge=1, le=20)
    recent_auth_seconds: int = Field(default=300, ge=60, le=900)
    oidc_max_auth_age_seconds: int = Field(default=3600, ge=300, le=43200)
    oidc_required_acr: str = "2"
    secret_files: dict[str, str] = Field(default_factory=dict)
    idp_token_key: SecretStr | None = None
    max_actor_active_runs: int = Field(default=8, ge=1, le=1000)
    max_tenant_active_runs: int = Field(default=64, ge=1, le=5000)
    max_global_active_runs: int = Field(default=128, ge=1, le=10000)
    login_per_minute: int = Field(default=30, ge=1, le=60)
    actor_requests_per_minute: int = Field(default=600, ge=10, le=1000)
    max_request_bytes: int = Field(default=65536, ge=4096, le=1048576)
    session_ttl_seconds: int = Field(default=28800, ge=60, le=86400)
    app_origin: str = "http://127.0.0.1:8091"
    oidc_issuer: str = "http://127.0.0.1:8181/realms/opspilot"
    oidc_internal_issuer: str = "http://oidc:8080/realms/opspilot"
    oidc_client_id: str = "opspilot-bff"
    allow_demo_self_approval: bool = False

    local_demo_tenant: UUID = DEMO_TENANT

    app_env: Literal["local", "test", "production"] = "local"
    workflow_database_url: SecretStr | None = None
    domain_database_url: SecretStr | None = None
    checkpoint_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    mcp_url: str = "http://mcp:8001/mcp"
    mcp_service_token: SecretStr = SecretStr("")
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
    clarification_ttl_seconds: int = Field(default=86400, ge=1, le=604800)
    demo_timezone: str = "Asia/Jerusalem"

    @model_validator(mode="before")
    @classmethod
    def load_secret_files(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        mapping = value.get("secret_files", {})
        if isinstance(mapping, str):
            import json

            mapping = json.loads(mapping)
        if not isinstance(mapping, dict):
            raise ValueError("Secret files must be a mapping")
        allowed = {
            "session_signing_key",
            "mcp_service_token",
            "idp_token_key",
            "redis_password",
            "cache_signing_key",
            "openai_api_key",
            "identity_database_url",
            "workflow_database_url",
            "checkpoint_database_url",
            "domain_database_url",
            "migration_database_url",
        }
        for name, file in mapping.items():
            if name not in allowed or value.get(name):
                raise ValueError("Invalid or ambiguous secret file configuration")
            path = Path(file)
            if not path.is_absolute() or not path.is_file() or path.stat().st_size > 16384:
                raise ValueError("Secret file unavailable or oversized")
            value[name] = path.read_text().strip()
        return value

    @model_validator(mode="after")
    def enforce_security_profile(self) -> Self:
        if self.app_env == "production" and self.security_profile != "hardened":
            raise ValueError("Production requires hardened security profile")
        if self.security_profile != "hardened":
            return self
        origins = [self.mcp_url] if self.security_role in {"api", "worker"} else []
        if self.security_role == "api":
            origins += [self.app_origin, self.oidc_issuer, self.oidc_internal_issuer]
        if self.otel_endpoint:
            origins.append(self.otel_endpoint)
        if self.jaeger_url:
            origins += [self.jaeger_url, self.jaeger_query_url]
        for value in origins:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Hardened connections require trusted HTTPS origins")
        origin = urlsplit(self.app_origin)
        if origin.path not in {"", "/"} or origin.query or origin.fragment:
            raise ValueError("APP_ORIGIN must be an origin")
        if self.security_role == "api" and origin.hostname == urlsplit(self.oidc_issuer).hostname:
            raise ValueError("Application and IdP require distinct hostnames")
        if self.allow_demo_self_approval:
            raise ValueError("Demo self approval forbidden in hardened profile")
        if self.security_role == "api" and not self.idp_token_key:
            raise ValueError("Hardened profile requires token encryption key")
        if self.idp_token_key:
            Fernet(self.idp_token_key.get_secret_value().encode())
        if self.security_role == "api" and len(self.session_signing_key.get_secret_value()) < 64:
            raise ValueError("Strong session signing key required")
        if self.session_ttl_seconds > 43200 or self.session_idle_seconds > 1800:
            raise ValueError("Session policy exceeds AAL2 bounds")
        if (
            self.max_actor_active_runs > 8
            or self.max_tenant_active_runs > 64
            or self.max_global_active_runs > 128
        ):
            raise ValueError("Explicit bounded production admission policy required")
        for name in [
            "identity_database_url",
            "workflow_database_url",
            "checkpoint_database_url",
            "domain_database_url",
            "migration_database_url",
        ]:
            dsn = getattr(self, name)
            if dsn and make_url(dsn.get_secret_value()).query.get("sslmode") != "verify-full":
                raise ValueError("Hardened database clients require sslmode=verify-full")
        return self

    @field_validator("mcp_service_token")
    @classmethod
    def validate_token(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        token = value.get_secret_value()
        if not token and info.data.get("security_profile") == "hardened":
            return value
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
        "identity_database_url",
    )
    @classmethod
    def validate_dsn(cls, value: SecretStr | None) -> SecretStr | None:
        if (
            value is not None
            and make_url(value.get_secret_value()).drivername != "postgresql+psycopg"
        ):
            raise ValueError("Use a postgresql+psycopg URL")
        return value

    def database_url(
        self, role: Literal["workflow", "domain", "checkpoint", "migration", "identity"]
    ) -> str:
        value = getattr(self, f"{role}_database_url")
        if not isinstance(value, SecretStr):
            raise ValueError(f"Missing {role} database URL")
        return value.get_secret_value()
