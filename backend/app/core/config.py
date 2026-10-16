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

    # Object storage. "filesystem" locally and in tests; "s3" for MinIO in
    # compose and Kubernetes.
    storage_backend: str = "filesystem"
    storage_path: str = "./var/artifacts"
    s3_endpoint: str = "minio:9000"
    s3_bucket: str = "cerebro-artifacts"
    s3_access_key: str = "cerebro"
    s3_secret_key: str = "cerebro_dev_password"
    s3_secure: bool = False

    # Embeddings. "auto" is the default: use a pretrained embedder from the
    # local Ollama daemon when one is installed, and the deterministic
    # hashing embedder when it is not. "hashing" and "ollama" pin the choice
    # — the test suite pins hashing so its vectors are reproducible. There is
    # no cloud provider, by design.
    #
    # Note that provider, model and width are stored with every vector and
    # search filters on all three, so a change of provider orphans existing
    # vectors until they are backfilled. That is why the active provider and
    # the number of fragments missing a vector for it are reported by
    # /api/ml/status rather than left to be discovered through empty results.
    embedding_provider: str = "auto"
    embedding_dimensions: int = 384
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_embedding_dimensions: int = 768

    # Metadata enrichment. Deterministic enrichment (the document's own
    # metadata plus statistics over its text) always runs. A local language
    # model is used automatically when the Ollama daemon is running and has
    # one; "off" pins it to deterministic enrichment only. No cloud option,
    # by design.
    enrichment_llm: str = "auto"
    ollama_enrichment_model: str = "llama3.2"

    # Assisted Recollection. Retrieval always runs; this adds a local model
    # to phrase an answer from the retrieved passages. "auto" uses whatever
    # the local daemon has; "off" returns the passages only. It used to
    # default to off, which made a working feature look like a broken one.
    # No cloud option, by design.
    recall_llm: str = "auto"
    ollama_recall_model: str = "llama3.2"

    # Upload limits
    max_upload_bytes: int = 25 * 1024 * 1024

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
