"""Fixtures for risk management tests."""

from datetime import UTC, datetime

from exness_bot.domain.enums import SignalAction, Timeframe
from exness_bot.domain.models import AccountInfo, IndicatorSnapshot, Signal, SymbolInfo
from exness_bot.risk.models import RiskState


def make_account(
    *,
    equity: float = 10_000.0,
    free_margin: float = 9_000.0,
    leverage: int = 500,
    trade_mode: str = "demo",
) -> AccountInfo:
    return AccountInfo(
        login=12345678,
        balance=equity,
        equity=equity,
        margin=equity - free_margin,
        free_margin=free_margin,
        leverage=leverage,
        trade_mode=trade_mode,
    )


def make_xauusd_symbol(
    *,
    bid: float = 2350.10,
    ask: float = 2350.30,
    spread: int = 20,
    volume_max: float = 100.0,
) -> SymbolInfo:
    return SymbolInfo(
        symbol="XAUUSD",
        bid=bid,
        ask=ask,
        point=0.01,
        digits=2,
        volume_min=0.01,
        volume_max=volume_max,
        volume_step=0.01,
        trade_contract_size=100.0,
        spread=spread,
        trade_mode=4,
        visible=True,
    )


def make_buy_signal(
    *,
    entry_price: float = 2350.0,
    atr_14: float | None = 2.0,
    rsi_14: float = 60.0,
) -> Signal:
    indicators = IndicatorSnapshot(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ema_20=110.0,
        ema_50=105.0,
        ema_200=100.0,
        rsi_14=rsi_14,
        atr_14=atr_14,
    )
    return Signal.create(
        action=SignalAction.BUY,
        strategy_name="ema_rsi_atr_v1",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        entry_price=entry_price,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        indicators=indicators,
        reason="test buy",
    )


def make_risk_state(
    *,
    day_start_equity: float = 10_000.0,
    peak_equity: float = 10_000.0,
) -> RiskState:
    return RiskState(day_start_equity=day_start_equity, peak_equity=peak_equity)
