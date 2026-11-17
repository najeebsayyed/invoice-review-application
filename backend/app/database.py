"""Database engine and session management using SQLAlchemy 2."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy database models."""

    pass


def normalize_database_url(url: str) -> str:
    """Normalize database connection string for SQLAlchemy 2.0 dialects with driver fallback."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Check whether psycopg is available and functional (native C library)
    psycopg_available = False
    try:
        import psycopg.pq  # noqa: F401

        psycopg_available = True
    except Exception:
        psycopg_available = False

    if url.startswith("postgresql://"):
        driver = "postgresql+psycopg://" if psycopg_available else "postgresql+pg8000://"
        return url.replace("postgresql://", driver, 1)

    if url.startswith("postgresql+psycopg://") and not psycopg_available:
        return url.replace("postgresql+psycopg://", "postgresql+pg8000://", 1)

    return url


def build_database(database_url: str) -> tuple[Engine, sessionmaker]:
    """Create a configured SQLAlchemy engine and sessionmaker."""
    normalized_url = normalize_database_url(database_url)
    connect_args: dict[str, Any] = {}
    engine_kwargs: dict[str, Any] = {}

    if normalized_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # Cloud databases (e.g. Azure PostgreSQL) drop idle connections; pre-ping tests them
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 300

    engine = create_engine(normalized_url, connect_args=connect_args, **engine_kwargs)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
