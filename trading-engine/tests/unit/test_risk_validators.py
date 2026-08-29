"""Unit tests for risk validators."""

from exness_bot.config.settings import Settings
from exness_bot.risk.validators import (
    check_daily_loss,
    check_drawdown,
    check_margin,
    check_max_open_positions,
    check_missing_account,
    check_missing_symbol,
    check_spread,
    check_trading_mode,
    estimate_required_margin,
)
from tests.fixtures.risk_data import make_account, make_xauusd_symbol


class TestCheckMissingAccount:
    def test_none_account(self) -> None:
        assert check_missing_account(None) == "Account information unavailable"

    def test_zero_equity(self) -> None:
        account = make_account(equity=0, free_margin=0)
        assert check_missing_account(account) == "Account equity must be positive"


class TestCheckMissingSymbol:
    def test_none_symbol(self) -> None:
        assert check_missing_symbol(None) == "Symbol specification unavailable"

    def test_invalid_point(self) -> None:
        symbol = make_xauusd_symbol()
        invalid = symbol.model_copy(update={"point": 0.0})
        assert check_missing_symbol(invalid) == "Symbol point size unavailable or invalid"


class TestDailyLossAndDrawdown:
    def test_daily_loss_boundary_not_exceeded(self) -> None:
        assert check_daily_loss(9801.0, 10_000.0, 2.0) is None

    def test_daily_loss_boundary_exceeded(self) -> None:
        assert check_daily_loss(9799.0, 10_000.0, 2.0) == "Maximum daily loss exceeded"

    def test_drawdown_boundary_not_exceeded(self) -> None:
        assert check_drawdown(9501.0, 10_000.0, 5.0) is None

    def test_drawdown_boundary_exceeded(self) -> None:
        assert check_drawdown(9499.0, 10_000.0, 5.0) == "Maximum drawdown exceeded"


class TestSpread:
    def test_spread_within_limit(self) -> None:
        assert check_spread(make_xauusd_symbol(spread=20), 50) is None

    def test_spread_exceeds_limit(self) -> None:
        reason = check_spread(make_xauusd_symbol(spread=80), 50)
        assert reason is not None
        assert "Spread too wide" in reason


class TestTradingMode:
    def test_demo_mode_allowed(self) -> None:
        settings = Settings(TRADING_MODE="demo")
        assert check_trading_mode(settings, make_account()) is None

    def test_live_without_allow_flag(self) -> None:
        from exness_bot.config.settings import TradingMode

        settings = Settings.model_construct(
            trading_mode=TradingMode.LIVE,
            allow_live_trading=False,
            dry_run=False,
        )
        reason = check_trading_mode(settings, make_account())
        assert reason is not None
        assert "ALLOW_LIVE_TRADING" in reason

    def test_live_on_demo_account_rejected(self) -> None:
        from exness_bot.config.settings import TradingMode

        settings = Settings.model_construct(
            trading_mode=TradingMode.LIVE,
            allow_live_trading=True,
            dry_run=False,
        )
        reason = check_trading_mode(settings, make_account(trade_mode="demo"))
        assert reason == "Live trading mode cannot use a demo account"


class TestMargin:
    def test_insufficient_margin(self) -> None:
        reason = check_margin(required_margin=10_000.0, free_margin=1_000.0)
        assert reason is not None
        assert "Insufficient free margin" in reason

    def test_missing_leverage(self) -> None:
        assert estimate_required_margin(
            volume=0.1,
            entry_price=2350.0,
            symbol=make_xauusd_symbol(),
            leverage=0,
        ) is None


class TestMaxOpenPositions:
    def test_at_limit_rejects(self) -> None:
        from datetime import UTC, datetime

        from exness_bot.domain.enums import SignalDirection
        from exness_bot.domain.models import Position

        positions = [
            Position(
                ticket=1,
                symbol="XAUUSD",
                volume=0.01,
                direction=SignalDirection.LONG,
                open_price=2350.0,
                current_price=2351.0,
                open_time=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
        reason = check_max_open_positions(positions, "XAUUSD", max_open_positions=1)
        assert reason is not None
