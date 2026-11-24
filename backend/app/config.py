from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    # JSON logs by default in production, human-readable otherwise
    log_json: bool | None = None

    # --- Database
    database_url: str = "postgresql+asyncpg://docformatter:docformatter@127.0.0.1:5434/docformatter"
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # --- LLM
    ollama_url: str = "http://192.168.0.84:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_timeout: float = 600.0  # seconds to wait between streamed tokens
    chunk_chars: int = 24000  # longer documents are formatted in sequential chunks
    max_concurrent_jobs: int = 1  # LLM jobs running at once (GPU bound); others queue
    max_queued_jobs: int = 20  # running + waiting jobs; beyond this new requests get HTTP 429

    # --- Limits
    max_input_chars: int = 300_000
    max_upload_mb: int = 20

    # --- HTTP (only needed when the UI is served from a different origin than the API)
    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def json_logs(self) -> bool:
        return self.is_production if self.log_json is None else self.log_json

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
