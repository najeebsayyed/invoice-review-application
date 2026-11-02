"""Database engine and session management using SQLAlchemy 2."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy database models."""

    pass


def build_database(database_url: str) -> tuple[Engine, sessionmaker]:
    """Create a configured SQLAlchemy engine and sessionmaker."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
