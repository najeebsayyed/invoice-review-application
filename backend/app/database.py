"""Database engine and session management using SQLAlchemy 2."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy database models."""

    pass


def normalize_database_url(url: str) -> str:
    """Normalize database connection string for SQLAlchemy 2.0 dialects."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
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
