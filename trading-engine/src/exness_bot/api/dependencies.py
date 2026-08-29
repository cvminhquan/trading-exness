"""FastAPI dependency injection."""

from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path

from exness_bot.api.services.account_runtime import AccountRuntime
from exness_bot.api.services.read_service import ReadService
from exness_bot.config.account_profiles import AccountProfileStore
from exness_bot.config.settings import Settings, get_settings
from exness_bot.data.factory import create_trading_data_provider

_read_service: ReadService | None = None
_read_service_lock = threading.Lock()

ENGINE_ROOT = Path(__file__).resolve().parents[3]


@lru_cache
def get_cached_settings() -> Settings:
    return get_settings()


def get_read_service() -> ReadService:
    """Return a process-wide ReadService so MT5 reconnect state is shared."""
    global _read_service
    with _read_service_lock:
        if _read_service is None:
            settings = get_cached_settings()
            store = AccountProfileStore(
                ENGINE_ROOT / ".mt5_active_account",
                default=settings.mt5_active_account,
            )
            provider = create_trading_data_provider(settings)
            runtime = AccountRuntime(settings, store, provider)
            runtime.apply_startup_credentials()
            _read_service = ReadService(
                settings,
                provider,
                project_root=ENGINE_ROOT,
                account_runtime=runtime,
            )
        return _read_service
