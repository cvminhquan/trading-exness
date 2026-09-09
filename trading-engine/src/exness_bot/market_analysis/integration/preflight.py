"""Read-only preflight for Phase 16.3.6 real AI integration.

Never prints GEMINI_API_KEY or other secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.analyst_chat.session import default_chat_data_root
from exness_bot.market_analysis.external_context.service import (
    default_external_data_root,
)
from exness_bot.market_analysis.synthesis.service import default_synthesis_data_root


def _key_configured(settings: Settings) -> bool:
    raw = (settings.gemini_api_key or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered in {"", "changeme", "your-key", "todo", "xxx"}:
        return False
    if raw.startswith("<") and raw.endswith(">"):
        return False
    return len(raw) >= 8


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe_16_3_6"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def run_preflight(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings()
    key_ok = _key_configured(settings)
    ext_root = default_external_data_root()
    syn_root = default_synthesis_data_root()
    chat_root = default_chat_data_root()

    mt5_connected = False
    technical_available = False
    technical_error: str | None = None
    try:
        from exness_bot.data.factory import create_trading_data_provider

        data = create_trading_data_provider(settings)
        # Prefer connection probe without dumping account numbers
        probe = getattr(data, "is_connected", None)
        if callable(probe):
            mt5_connected = bool(probe())
        elif getattr(settings, "data_source", None) is not None:
            # mock/backtest count as usable for technical snapshot path
            mt5_connected = str(settings.data_source).lower() in {
                "mock",
                "backtest",
                "mt5",
            }
            if str(settings.data_source).lower() == "mt5":
                # attempt lightweight account read if available
                getter = getattr(data, "get_account_snapshot", None) or getattr(
                    data, "get_account", None
                )
                if callable(getter):
                    try:
                        getter()
                        mt5_connected = True
                    except Exception as exc:
                        mt5_connected = False
                        technical_error = type(exc).__name__

        from exness_bot.market_analysis.technical_snapshot import (
            TechnicalSnapshotBuilder,
        )

        snap = TechnicalSnapshotBuilder(settings, data).build("XAUUSD")
        technical_available = bool(snap)
    except Exception as exc:
        technical_error = type(exc).__name__
        technical_available = False

    real_smoke_ready = bool(
        key_ok
        and settings.external_intelligence_enabled
        and settings.ai_market_synthesis_enabled
        and settings.ai_market_analyst_chat_enabled
        and technical_available
    )

    if not key_ok:
        block_reason = "GEMINI_API_KEY NOT CONFIGURED"
    elif not technical_available:
        block_reason = "TECHNICAL_SNAPSHOT_UNAVAILABLE"
    elif not (
        settings.external_intelligence_enabled
        and settings.ai_market_synthesis_enabled
        and settings.ai_market_analyst_chat_enabled
    ):
        block_reason = "LOCAL_FEATURE_FLAGS_OFF"
    else:
        block_reason = None

    return {
        "phase": "16.3.6",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "symbol": "XAUUSD",
        "gemini_api_key_configured": key_ok,
        "gemini_api_key_printed": False,
        "external_intelligence_enabled": bool(
            settings.external_intelligence_enabled
        ),
        "external_intelligence_provider": settings.external_intelligence_provider,
        "external_intelligence_model": settings.external_intelligence_model,
        "ai_market_synthesis_enabled": bool(settings.ai_market_synthesis_enabled),
        "ai_market_synthesis_provider": settings.ai_market_synthesis_provider,
        "ai_market_synthesis_model": settings.ai_market_synthesis_model,
        "ai_market_analyst_chat_enabled": bool(
            settings.ai_market_analyst_chat_enabled
        ),
        "ai_market_analyst_chat_provider": settings.ai_market_analyst_chat_provider,
        "ai_market_analyst_chat_model": settings.ai_market_analyst_chat_model,
        "data_source": str(getattr(settings, "data_source", "")),
        "mt5_connected": mt5_connected,
        "technical_snapshot_available": technical_available,
        "technical_error_type": technical_error,
        "external_cache_writable": _writable(ext_root),
        "synthesis_cache_writable": _writable(syn_root),
        "chat_session_store_writable": _writable(chat_root),
        "real_smoke_ready": real_smoke_ready,
        "block_reason": block_reason,
    }
