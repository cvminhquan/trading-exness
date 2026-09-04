"""Paper fill pricing from read-only quotes. Not a guaranteed SignalResult price."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.backtest.config import BacktestConfig
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import SymbolInfo


@dataclass(frozen=True)
class SimulatedFill:
    requested_price: float
    fill_price: float
    spread_points: int
    slippage_points: float


def simulate_entry_fill(
    *,
    side: SignalDirection,
    symbol: SymbolInfo,
    config: BacktestConfig,
    candle_spread: int | None = None,
) -> SimulatedFill:
    if candle_spread and candle_spread > 0:
        spread_points = int(candle_spread)
    else:
        spread_points = int(symbol.spread)
    if spread_points <= 0:
        spread_points = config.spread_points
    slip = config.slippage_points * config.point
    requested = round((symbol.bid + symbol.ask) / 2.0, 10)
    fill = symbol.ask + slip if side == SignalDirection.LONG else symbol.bid - slip
    return SimulatedFill(
        requested_price=requested,
        fill_price=round(fill, 10),
        spread_points=spread_points,
        slippage_points=config.slippage_points,
    )


def simulate_exit_fill(
    *,
    side: SignalDirection,
    trigger_price: float,
    config: BacktestConfig,
    symbol: SymbolInfo,
) -> float:
    spread_points = int(symbol.spread) if symbol.spread > 0 else config.spread_points
    cost = (spread_points * config.point / 2.0) + (config.slippage_points * config.point)
    if side == SignalDirection.LONG:
        return round(trigger_price - cost, 10)
    return round(trigger_price + cost, 10)
