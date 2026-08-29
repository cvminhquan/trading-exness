"""FastAPI dependency injection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from exness_bot.api.services.read_service import ReadService
from exness_bot.config.settings import Settings, get_settings
from exness_bot.data.factory import create_trading_data_provider


@lru_cache
def get_cached_settings() -> Settings:
    return get_settings()


def get_read_service() -> ReadService:
    settings = get_cached_settings()
    project_root = Path(__file__).resolve().parents[3]
    provider = create_trading_data_provider(settings)
    return ReadService(settings, provider, project_root=project_root)
