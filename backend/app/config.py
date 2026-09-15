from __future__ import annotations

import json

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_allowed_origins(value: str | list[str] | None) -> list[str]:
    if value is None:
        raise ValueError("ALLOWED_ORIGINS is required")

    if isinstance(value, list):
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("ALLOWED_ORIGINS cannot be empty")
        return cleaned

    raw = str(value).strip()
    if not raw:
        raise ValueError("ALLOWED_ORIGINS cannot be empty")

    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("ALLOWED_ORIGINS must be a list of origins")
        cleaned = [str(item).strip() for item in parsed if str(item).strip()]
        if not cleaned:
            raise ValueError("ALLOWED_ORIGINS cannot be empty")
        return cleaned

    cleaned = [item.strip() for item in raw.split(",") if item and item.strip()]
    if not cleaned:
        raise ValueError("ALLOWED_ORIGINS cannot be empty")
    return cleaned


class Settings(BaseSettings):
    app_name: str = "document-copilot-backend"
    environment: str = "development"
    api_version: str = "v1"

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    mistral_api_key: str
    mistral_embedding_model: str = "mistral-embed"
    mistral_embedding_dimensions: int = 1024
    mistral_chat_model: str = "mistral-small-latest"

    retrieval_top_k: int = 10
    retrieval_candidate_k: int = 50
    retrieval_rrf_k: int = 60
    retrieval_neighbor_window: int = 1
    retrieval_keyword_extraction_enabled: bool = True
    retrieval_keyword_extraction_timeout_ms: int = 6000

    mistral_request_timeout_ms: int = 15000
    chat_turn_timeout_seconds: int = 60
    chat_typing_delay_seconds: float = 0.008
    chat_typing_chunk_words: int = 4
    chat_heartbeat_interval_seconds: float = 6.0

    #khai báo là str, KHÔNG phải list[str],
    # để pydantic-settings không tự ý chạy json.loads() ở tầng đọc .env
    allowed_origins_raw: str = Field(default="", alias="ALLOWED_ORIGINS")

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url.strip()
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def allowed_origins(self) -> list[str]:
        return parse_allowed_origins(self.allowed_origins_raw)


settings = Settings()