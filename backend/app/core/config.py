"""Application configuration, loaded from the environment."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CEREBRO_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://cerebro:cerebro_dev_password@localhost:5432/cerebro"

    # JWT. The default is a development-only value; deployments must override
    # CEREBRO_JWT_SECRET, and non-development environments refuse to start without it.
    jwt_secret: str = "dev-only-insecure-secret-do-not-use-outside-local-development"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    # Session cookie
    cookie_name: str = "cerebro_session"
    cookie_secure: bool = False  # True behind HTTPS in any deployed environment
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None

    # CORS — the web origin(s) permitted to call this API with credentials
    cors_origins: str = "http://localhost:3000"

    environment: str = "development"

    @model_validator(mode="after")
    def _guard_production_secret(self) -> "Settings":
        if self.environment != "development":
            if self.jwt_secret.startswith("dev-only-"):
                raise ValueError(
                    "CEREBRO_JWT_SECRET must be set to a real secret outside development"
                )
            if len(self.jwt_secret) < 32:
                raise ValueError("CEREBRO_JWT_SECRET must be at least 32 characters")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
