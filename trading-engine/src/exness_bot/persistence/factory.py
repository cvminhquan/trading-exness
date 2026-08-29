"""Repository factory."""

from __future__ import annotations

import structlog

from exness_bot.config.settings import Settings
from exness_bot.persistence.repository import TradingRepository
from exness_bot.persistence.sqlite_repository import SQLiteTradingRepository, parse_sqlite_path

logger = structlog.get_logger(__name__)


def create_trading_repository(settings: Settings) -> TradingRepository:
    """
    Create a trading repository from settings.

    Phase 6 uses SQLite for idempotency and audit events. PostgreSQL URLs
    fall back to a local SQLite file until a Postgres driver is added.
    """
    database_url = settings.database_url
    if database_url.startswith("sqlite:"):
        path = parse_sqlite_path(database_url)
        return SQLiteTradingRepository(path)

    logger.warning(
        "repository_sqlite_fallback",
        requested_url=database_url,
        fallback_path="exness_bot_local.db",
        message="PostgreSQL persistence not yet implemented; using SQLite fallback",
    )
    return SQLiteTradingRepository("exness_bot_local.db")
