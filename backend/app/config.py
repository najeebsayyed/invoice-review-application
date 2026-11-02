"""Application settings and immutable configuration for Invoice Review."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_NAME = "gpt-5.6-terra"


@dataclass(frozen=True)
class AppConfig:
    """Immutable application and domain rules configuration."""

    expected_customer_name: str = "Northstar Facilities B.V."
    expected_customer_vat_id: str = "NL00449544B01"
    database_url: str = "sqlite:///./data/documents.db"
    upload_dir: Path = BACKEND_ROOT / "data" / "uploads"
    max_upload_bytes: int = 4 * 1024 * 1024
    min_field_confidence: float = 0.80


APP_CONFIG = AppConfig()


class Settings(BaseSettings):
    """Environment-based settings read exclusively from .env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    openai_model: str = DEPLOYMENT_NAME
    allowed_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
