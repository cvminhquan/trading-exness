"""Read-only DEMO account / symbol identity verification. No order_send."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from exness_bot.broker.mt5.mapper import map_account_info, map_symbol_info, map_tick
from exness_bot.config.settings import Settings
from exness_bot.data.freshness import QuoteFreshness, classify_quote_freshness
from exness_bot.domain.models import AccountInfo, SymbolInfo, Tick


@dataclass(frozen=True)
class DemoIdentitySnapshot:
    account: AccountInfo
    trade_allowed: bool
    currency: str
    server: str
    login: int
    trade_mode: str
    terminal_connected: bool | None = None
    terminal_trade_allowed: bool | None = None


@dataclass(frozen=True)
class DemoMarketSnapshot:
    symbol: SymbolInfo
    tick: Tick
    freshness: QuoteFreshness
    age_seconds: float
    spread_points: float


class DemoBrokerProbe(Protocol):
    """Read-only probe — implementations must not call order_send."""

    def fetch_account(self) -> DemoIdentitySnapshot: ...

    def fetch_market(self, broker_symbol: str) -> DemoMarketSnapshot: ...

    def list_positions(self, broker_symbol: str) -> tuple[dict[str, Any], ...]: ...


@dataclass
class StaticDemoBrokerProbe:
    """Test double — no MT5."""

    identity: DemoIdentitySnapshot
    market: DemoMarketSnapshot
    positions: tuple[dict[str, Any], ...] = ()

    def fetch_account(self) -> DemoIdentitySnapshot:
        return self.identity

    def fetch_market(self, broker_symbol: str) -> DemoMarketSnapshot:
        del broker_symbol
        return self.market

    def list_positions(self, broker_symbol: str) -> tuple[dict[str, Any], ...]:
        del broker_symbol
        return self.positions


class ReadOnlyMt5DemoProbe:
    """Uses MT5ReadOnlyClient only — never trading mutations."""

    def __init__(self, client: Any, *, stale_after_seconds: int = 10) -> None:
        self._client = client
        self._stale_after = stale_after_seconds

    def fetch_account(self) -> DemoIdentitySnapshot:
        raw = self._client.account_info()
        if raw is None:
            msg = "MT5 account_info unavailable"
            raise RuntimeError(msg)
        account = map_account_info(raw)
        trade_allowed = bool(getattr(raw, "trade_allowed", True))
        terminal_connected: bool | None = None
        terminal_trade_allowed: bool | None = None
        try:
            terminal = self._client.terminal_info()
        except Exception:
            terminal = None
        if terminal is not None:
            terminal_connected = bool(getattr(terminal, "connected", True))
            terminal_trade_allowed = bool(getattr(terminal, "trade_allowed", False))
            # Prefer terminal trade_allowed when available
            trade_allowed = trade_allowed and terminal_trade_allowed
        return DemoIdentitySnapshot(
            account=account,
            trade_allowed=trade_allowed,
            currency=account.currency,
            server=account.server,
            login=account.login,
            trade_mode=account.trade_mode,
            terminal_connected=terminal_connected,
            terminal_trade_allowed=terminal_trade_allowed,
        )

    def fetch_market(self, broker_symbol: str) -> DemoMarketSnapshot:
        raw_sym = self._client.symbol_info(broker_symbol)
        if raw_sym is None:
            msg = f"Broker symbol not found: {broker_symbol}"
            raise RuntimeError(msg)
        self._client.ensure_symbol_selected(broker_symbol)
        symbol = map_symbol_info(raw_sym)
        # Prefer tick for freshness
        raw_tick = self._client.symbol_info_tick(broker_symbol)
        if raw_tick is None:
            msg = f"No tick for {broker_symbol}"
            raise RuntimeError(msg)
        tick = map_tick(broker_symbol, raw_tick)
        now = datetime.now(tz=UTC)
        freshness = classify_quote_freshness(
            available=True,
            tick_time=tick.timestamp,
            now=now,
            stale_after_seconds=self._stale_after,
        )
        age = (now - tick.timestamp.astimezone(UTC)).total_seconds()
        spread = 0.0
        if symbol.point > 0:
            spread = (symbol.ask - symbol.bid) / symbol.point
        return DemoMarketSnapshot(
            symbol=symbol,
            tick=tick,
            freshness=freshness,
            age_seconds=age,
            spread_points=spread,
        )

    def list_positions(self, broker_symbol: str) -> tuple[dict[str, Any], ...]:
        rows = self._client.positions_get(symbol=broker_symbol)
        if not rows:
            return ()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "ticket": int(getattr(row, "ticket", 0)),
                    "symbol": str(getattr(row, "symbol", "")),
                    "volume": float(getattr(row, "volume", 0)),
                    "price_open": float(getattr(row, "price_open", 0)),
                    "sl": float(getattr(row, "sl", 0)),
                    "tp": float(getattr(row, "tp", 0)),
                    "type": int(getattr(row, "type", -1)),
                }
            )
        return tuple(out)


def resolve_broker_symbol_explicit(settings: Settings) -> str:
    """Explicit map only — no fuzzy discovery."""
    from exness_bot.broker.mt5.executor import parse_symbol_map, resolve_broker_symbol

    mapping = parse_symbol_map(
        settings.live_symbol_map,
        fallback_canonical=settings.symbol,
        fallback_broker=settings.mt5_symbol,
    )
    broker = resolve_broker_symbol(settings.symbol, mapping)
    if broker is None:
        msg = (
            f"Explicit symbol mapping missing for {settings.symbol!r}. "
            "Set LIVE_SYMBOL_MAP or MT5_SYMBOL."
        )
        raise RuntimeError(msg)
    return broker
