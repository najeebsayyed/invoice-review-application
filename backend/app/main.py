"""FastAPI application entry point for Invoice Review."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.accounting.routes import router as accounting_router
from app.config import APP_CONFIG, get_settings
from app.database import build_database
from app.documents.models import DocumentRecord
from app.documents.routes import router as document_router


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    config = APP_CONFIG
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    if config.database_url.startswith("sqlite:///"):
        db_path = config.database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = build_database(config.database_url)
    DocumentRecord.metadata.create_all(engine)

    settings = get_settings()

    app = FastAPI(
        title="Invoice Review API",
        version="0.1.0",
        description=(
            "FastAPI service for invoice & receipt processing, validation against "
            "Northstar policy, and General Ledger account suggestion."
        ),
    )
    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(document_router)
    app.include_router(accounting_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
