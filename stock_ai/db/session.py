from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, select, text
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
    from stock_ai.models import alerts, daily_run, latest_quote, market_data, news, positions, predictions, watchlist  # noqa: F401

    engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)
    news.ensure_news_schema(engine)
    positions.ensure_positions_schema(engine)
    from stock_ai.services.positions import migrate_legacy_positions, rebuild_position, _lock_ledger

    with get_session_factory(settings)() as db:
        try:
            _lock_ledger(db)
            migrate_legacy_positions(db, commit=False)
            # Upgrade existing ledgers to the residual-cent allocation too.
            rows = list(db.scalars(select(positions.Position).where(positions.Position.remaining_cost_basis.is_(None))))
            for position in rows:
                rebuild_position(db, position.ticker)
            db.commit()
        except Exception:
            db.rollback()
            raise
    if engine.dialect.name == "sqlite":
        # Existing databases had a non-unique ticker index. Consolidation above
        # preserves their balances before upgrading the projection constraint.
        with engine.begin() as connection:
            connection.execute(text("DROP INDEX IF EXISTS ix_positions_ticker"))
            connection.execute(text("CREATE UNIQUE INDEX ix_positions_ticker ON positions (ticker)"))


def get_db() -> Iterator[Session]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
