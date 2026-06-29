"""Central, 12-factor configuration. All settings come from env (prefix ``WB_``).

Nothing secret is ever hard-coded; ``.env.example`` documents the shape.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    env: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    max_graph_iterations: int = 12
    request_cost_budget_usd: float = 0.50

    # --- LLM ---
    llm_provider: Literal["openai", "anthropic", "gemini"] = "openai"
    # Leave model/embedding unset to use the provider's sensible default.
    llm_model: str | None = None
    embedding_model: str | None = None
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None

    # --- Travel providers ---
    # Flights: Amadeus self-service is decommissioned; Duffel is the default.
    flight_provider: Literal["duffel", "amadeus"] = "duffel"
    geo_provider: Literal["openmeteo", "amadeus"] = "openmeteo"
    # Hotels: duffel (Stays, needs access) | tavily (web suggestions) | amadeus | none
    hotel_provider: Literal["duffel", "tavily", "amadeus", "none"] = "duffel"

    # Duffel (https://app.duffel.com/join -> Developers -> Access tokens)
    duffel_api_key: SecretStr | None = None
    duffel_version: str = "v2"
    # In Duffel sandbox, test hotels ONLY appear at coords -24.38,-128.32.
    # Enable this to route Stays searches there so hotels populate in the demo.
    duffel_use_test_hotels: bool = False

    # Amadeus (legacy / optional)
    amadeus_client_id: SecretStr | None = None
    amadeus_client_secret: SecretStr | None = None
    amadeus_env: Literal["test", "production"] = "test"

    # --- External providers ---
    tavily_api_key: SecretStr | None = None
    google_maps_api_key: SecretStr | None = None
    openweather_api_key: SecretStr | None = None
    exchange_rates_base_url: str = "https://api.frankfurter.dev/v1"

    # --- Infra ---
    database_url: str = "postgresql://wanderbot:wanderbot@localhost:5432/wanderbot"
    redis_url: str = "redis://localhost:6379/0"
    sqlite_path: str = "wanderbot.db"  # app store fallback (dev): users + saved plans
    # App store DB. Unset -> SQLite (zero-config dev). Set to a Postgres URL in
    # prod (the API runs read-only, so SQLite isn't writable there).
    app_store_url: str | None = None

    # --- Security ---
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-in-prod"))
    jwt_algorithm: str = "HS256"

    # --- MCP ---
    mcp_server_cmd: str = "python -m mcp_server.server"

    # --- Observability ---
    otel_exporter_otlp_endpoint: str | None = None

    # --- Guardrails (AWS Bedrock) ---
    guardrails_backend: Literal["auto", "regex", "bedrock"] = "auto"
    aws_region: str = "us-east-1"
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str = "DRAFT"

    @property
    def bedrock_guardrails_enabled(self) -> bool:
        if self.guardrails_backend == "regex":
            return False
        if self.guardrails_backend == "bedrock":
            return True
        return self.bedrock_guardrail_id is not None  # auto

    # Treat blank env values (e.g. WB_TAVILY_API_KEY=) as "not configured" so a
    # provider is cleanly disabled instead of sending empty credentials.
    @field_validator(
        "openai_api_key",
        "google_api_key",
        "duffel_api_key",
        "amadeus_client_id",
        "amadeus_client_secret",
        "tavily_api_key",
        "google_maps_api_key",
        "openweather_api_key",
        "bedrock_guardrail_id",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def amadeus_base_url(self) -> str:
        """Select Amadeus host by env. Identical code path for test vs prod."""
        if self.amadeus_env == "production":
            return "https://api.amadeus.com"
        return "https://test.api.amadeus.com"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton so env is parsed once per process."""
    return Settings()
