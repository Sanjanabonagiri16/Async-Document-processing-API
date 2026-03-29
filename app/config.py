from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://docuser:docpass@localhost:5432/docjobs"
    redis_url: str = "redis://localhost:6379/0"

    # If set, added to OpenAPI "Servers" so Swagger Try it out uses this host (e.g. https://api.example.com)
    public_base_url: str | None = Field(default=None, validation_alias="API_PUBLIC_BASE_URL")

    @field_validator("public_base_url", mode="before")
    @classmethod
    def _empty_public_url_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    api_rate_limit: str = "60/minute"
    read_rate_limit: str = "120/minute"

    # Simulated failure rate for demo retry path (0.0 = never fail randomly)
    simulate_random_failure_rate: float = 0.0


settings = Settings()
