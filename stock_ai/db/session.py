from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from stock_ai.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    sqlite_path = database_url.replace("sqlite:///", "", 1)
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)


def get_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    database_url = settings.database_url

    if database_url not in _ENGINE_CACHE:
        _ensure_sqlite_parent(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        _ENGINE_CACHE[database_url] = create_engine(database_url, connect_args=connect_args)

    return _ENGINE_CACHE[database_url]


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    database_url = settings.database_url

    if database_url not in _SESSION_FACTORY_CACHE:
        _SESSION_FACTORY_CACHE[database_url] = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    return _SESSION_FACTORY_CACHE[database_url]


def init_db(settings: Settings | None = None) -> None:
    from stock_ai.models import alerts, market_data, news, positions, predictions, watchlist  # noqa: F401

    Base.metadata.create_all(bind=get_engine(settings))


def get_db() -> Iterator[Session]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
