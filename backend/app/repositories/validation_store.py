"""Shared SQLAlchemy store for validation and backtest records.

The current validation lab and persisted backtest metadata share one SQLite
database so historical records stay together.  The default file name remains
``paper_trade.db`` for backward compatibility with existing local data, but
new code should refer to it through ``Config.VALIDATION_DB_URL``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from ..config import Config

Base = declarative_base()

_engine = None
_SessionLocal = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _database_url() -> str:
    return Config.VALIDATION_DB_URL


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(_database_url(), future=True)
        Base.metadata.create_all(_engine)
        _SessionLocal = scoped_session(sessionmaker(bind=_engine, expire_on_commit=False, future=True))
    return _engine


def get_session():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
