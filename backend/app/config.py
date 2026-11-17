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
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'data' / 'documents.db').as_posix()}"
    upload_dir: Path = BACKEND_ROOT / "data" / "uploads"
    max_upload_bytes: int = 4 * 1024 * 1024
    min_field_confidence: float = 0.80


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
    allowed_origins: str = (
        "http://localhost:5173,"
        "http://localhost:4173,"
        "https://invoice-review-app.najeebsayyed.in"
    )
    cors_origin_regex: str | None = r"^https:\/\/.*\.azurestaticapps\.net$"
    database_url: str | None = None
    upload_dir: Path | None = None
    azure_storage_connection_string: str | None = Field(default=None)
    azure_storage_container_name: str = "invoices"
    port: int = 8000
    host: str = "0.0.0.0"

    @property
    def cors_origins(self) -> list[str]:
        """Aggregate allowed origins from both single and multi-origin configuration."""
        origins: set[str] = set()
        for raw in (self.allowed_origins, self.allowed_origin):
            if raw:
                for item in raw.split(","):
                    cleaned = item.strip().rstrip("/")
                    if cleaned:
                        origins.add(cleaned)
        return sorted(origins)

    def resolve_frontend_dist(self) -> Path | None:
        """Resolve built frontend static assets directory if available."""
        for candidate in (
            BACKEND_ROOT.parent / "frontend" / "dist",
            Path("/app/frontend/dist"),
        ):
            if candidate.is_dir():
                return candidate
        return None


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()


def get_app_config(settings: Settings | None = None) -> AppConfig:
    """Construct AppConfig using optional runtime Settings overrides."""
    s = settings or get_settings()
    db_url = s.database_url or f"sqlite:///{(BACKEND_ROOT / 'data' / 'documents.db').as_posix()}"
    up_dir = s.upload_dir or (BACKEND_ROOT / "data" / "uploads")
    return AppConfig(
        database_url=db_url,
        upload_dir=up_dir,
    )


APP_CONFIG = get_app_config()
