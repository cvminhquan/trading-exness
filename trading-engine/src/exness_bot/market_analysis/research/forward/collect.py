"""Manual idempotent read-only MT5 forward collector.

Never calls order_send. Never mutates broker positions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.forward.protocol import (
    OBSERVED_DATA_CUTOFF_UTC,
    ensure_utc,
)
from exness_bot.market_analysis.research.forward.store import (
    DEFAULT_SYMBOL,
    append_forward_candles,
    default_forward_root,
    load_forward_candles,
)
from exness_bot.market_data.candles import is_candle_closed
from exness_bot.tools.export_history.serializer import timestamp_from_rate_row


def rates_to_candles(rates: Any, *, symbol: str) -> list[Candle]:
    """Convert MT5 rates ndarray to domain Candle list (UTC)."""
    if rates is None or len(rates) == 0:
        return []
    dtype_names = rates.dtype.names or ()
    out: list[Candle] = []
    for row in rates:
        ts = timestamp_from_rate_row(row)
        tick = float(row["tick_volume"]) if "tick_volume" in dtype_names else 0.0
        real = float(row["real_volume"]) if "real_volume" in dtype_names else 0.0
        spread = int(row["spread"]) if "spread" in dtype_names else 0
        out.append(
            Candle(
                symbol=symbol,
                timeframe=Timeframe.M15,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=tick,
                spread=spread,
                tick_volume=tick,
                real_volume=real,
            )
        )
    return out


def collect_forward_from_candles(
    candles: list[Candle],
    *,
    symbol: str = DEFAULT_SYMBOL,
    root: Path | None = None,
    now: datetime | None = None,
    source: str = "manual_or_replay",
    broker_symbol: str | None = None,
    broker_server: str | None = None,
) -> dict[str, Any]:
    """Append closed post-cutoff candles into forward store (idempotent)."""
    return append_forward_candles(
        candles,
        symbol=symbol,
        root=root or default_forward_root(),
        now=now,
        source=source,
        broker_symbol=broker_symbol,
        broker_server=broker_server,
    )


def collect_forward_from_mt5(
    *,
    symbol: str = DEFAULT_SYMBOL,
    root: Path | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Fetch CLOSED M15 bars after cutoff via existing read-only exporter stack."""
    from exness_bot.broker.mt5.client import MT5Client
    from exness_bot.config.settings import Settings
    from exness_bot.tools.export_history.fetcher import fetch_historical_rates
    from exness_bot.tools.export_history.symbol_resolver import resolve_broker_symbol

    settings = Settings()
    client = MT5Client(settings)
    now = end or datetime.now(tz=UTC)

    # Start just after cutoff; backfill from last stored candle if present
    existing = load_forward_candles(symbol, root=root)
    if existing:
        start = ensure_utc(existing[-1].timestamp) + timedelta(minutes=15)
    else:
        start = OBSERVED_DATA_CUTOFF_UTC + timedelta(seconds=1)

    if start >= now:
        return {
            "added": 0,
            "total": len(existing),
            "note": "no_new_range",
            "start": start.isoformat(),
            "end": now.isoformat(),
        }

    try:
        if not client.is_initialized:
            client.initialize()
        if not client.is_logged_in:
            client.login()
        broker_symbol = resolve_broker_symbol(client, symbol)
        server = None
        terminal = client.terminal_info()
        if terminal is not None:
            server = getattr(terminal, "name", None) or getattr(terminal, "company", None)
        rates = fetch_historical_rates(
            client,
            symbol=broker_symbol,
            timeframe=Timeframe.M15,
            start=start,
            end=now,
        )
        candles = rates_to_candles(rates, symbol=symbol)
        # Drop forming candle
        candles = [
            c for c in candles if is_candle_closed(c.timestamp, Timeframe.M15, now=now)
        ]
        result = collect_forward_from_candles(
            candles,
            symbol=symbol,
            root=root,
            now=now,
            source="mt5_read_only_copy_rates",
            broker_symbol=broker_symbol,
            broker_server=str(server) if server else None,
        )
        result["broker_symbol"] = broker_symbol
        result["fetch_start"] = start.isoformat()
        result["fetch_end"] = now.isoformat()
        return result
    finally:
        client.shutdown()


# Static audit helpers — research forward must not import execution mutators.
FORBIDDEN_IMPORT_NAMES = (
    "order_send",
    "LiveMT5ExecutionTransport",
    "MT5Executor",
    "ExecutionOrchestrator",
    "GatedMT5ExecutionPort",
    "CandidateExecutionService",
)
