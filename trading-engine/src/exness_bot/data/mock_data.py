"""Static mock data aligned with Dashboard mock fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, ClosedTrade, Position

STRATEGY = "ema_rsi_atr_v1"
SYMBOL = "XAUUSD"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def mock_account() -> AccountInfo:
    return AccountInfo(
        login=12345678,
        balance=10_842.5,
        equity=10_956.3,
        margin=412.0,
        free_margin=10_544.3,
        currency="USD",
        leverage=500,
        name="Demo Account",
        server="Exness-MT5Trial",
        trade_mode="demo",
    )


def mock_positions() -> list[Position]:
    opened = _now() - timedelta(hours=18)
    return [
        Position(
            ticket=1001,
            symbol=SYMBOL,
            volume=0.12,
            direction=SignalDirection.LONG,
            open_price=2348.5,
            current_price=2354.2,
            stop_loss=2336.0,
            take_profit=2373.0,
            profit=68.4,
            swap=-0.5,
            open_time=opened,
        )
    ]


def mock_closed_trades() -> list[ClosedTrade]:
    now = _now()
    return [
        ClosedTrade(
            id="tr-105",
            symbol=SYMBOL,
            strategy=STRATEGY,
            direction=SignalDirection.LONG,
            volume=0.1,
            entry_price=2339.2,
            exit_price=2351.8,
            gross_pnl=126.0,
            commission=4.2,
            swap=0.0,
            net_pnl=121.8,
            exit_reason="take_profit",
            closed_at=now - timedelta(hours=2),
            r_multiple=1.85,
        ),
        ClosedTrade(
            id="tr-104",
            symbol=SYMBOL,
            strategy=STRATEGY,
            direction=SignalDirection.SHORT,
            volume=0.08,
            entry_price=2358.4,
            exit_price=2352.1,
            gross_pnl=50.4,
            commission=3.6,
            swap=0.0,
            net_pnl=46.8,
            exit_reason="take_profit",
            closed_at=now - timedelta(hours=8),
            r_multiple=0.92,
        ),
        ClosedTrade(
            id="tr-103",
            symbol=SYMBOL,
            strategy=STRATEGY,
            direction=SignalDirection.SHORT,
            volume=0.08,
            entry_price=2362.0,
            exit_price=2368.4,
            gross_pnl=-51.2,
            commission=3.8,
            swap=0.0,
            net_pnl=-55.0,
            exit_reason="stop_loss",
            closed_at=now - timedelta(hours=26),
            r_multiple=-1.02,
        ),
    ]
