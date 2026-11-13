"""FastAPI application entry point for Invoice Review."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine, text

from app.accounting.routes import router as accounting_router
from app.config import APP_CONFIG, get_settings
from app.database import build_database
from app.documents.models import DocumentRecord
from app.documents.routes import router as document_router


def _sync_sqlite_schema(engine: Engine) -> None:
    """Ensure SQLite table schema contains all columns defined on DocumentRecord."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(documents)"))
        existing_cols = {row[1] for row in result.fetchall()}
        if existing_cols:
            for column in DocumentRecord.__table__.columns:
                if column.name not in existing_cols:
                    col_type = column.type.compile(engine.dialect)
                    conn.execute(
                        text(f"ALTER TABLE documents ADD COLUMN {column.name} {col_type}")
                    )
            # Ensure workspace indexes exist for fast query isolation
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_documents_workspace_id "
                    "ON documents (workspace_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_documents_workspace_created "
                    "ON documents (workspace_id, created_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_documents_workspace_duplicate_key "
                    "ON documents (workspace_id, normalized_vendor_name, normalized_invoice_number)"
                )
            )
            conn.commit()


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    config = APP_CONFIG
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    if config.database_url.startswith("sqlite:///"):
        db_path = config.database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = build_database(config.database_url)
    DocumentRecord.metadata.create_all(engine)
    _sync_sqlite_schema(engine)

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

    frontend_dist = settings.resolve_frontend_dist()
    if frontend_dist is not None:
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail="API route not found.")
            candidate = frontend_dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
