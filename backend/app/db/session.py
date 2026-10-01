"""Database engine and request-scoped session setup."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


SQLITE_URL = "sqlite:///./intellistock.db"


def _create_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    elif database_url.startswith(("postgresql://", "postgresql+")):
        connect_args = {"connect_timeout": 2}
    else:
        connect_args = {}
    return create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


def _get_engine() -> Engine:
    database_url = settings.database_url
    if not database_url.startswith(("postgresql://", "postgresql+")):
        return _create_engine(database_url)

    candidate = _create_engine(database_url)
    try:
        with candidate.connect():
            return candidate
    except SQLAlchemyError:
        candidate.dispose()
        return _create_engine(SQLITE_URL)


engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
