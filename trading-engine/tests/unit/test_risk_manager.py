"""Unit tests for RiskManager integration."""

from datetime import UTC, datetime

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalAction, SignalDirection, TradeAction
from exness_bot.domain.models import ApprovedOrderPlan, Position, RejectedSignal
from exness_bot.risk.decision import is_risk_approved, risk_rejection_reason
from exness_bot.risk.manager import RiskManager
from tests.fixtures.risk_data import (
    make_account,
    make_buy_signal,
    make_risk_state,
    make_xauusd_symbol,
)


def _manager(**settings: object) -> RiskManager:
    return RiskManager(Settings(**settings))


class TestRiskManagerApproval:
    def test_buy_signal_approved(self) -> None:
        decision = _manager().assess(
            make_buy_signal(),
            make_account(),
            make_xauusd_symbol(),
            [],
            make_risk_state(),
        )
        assert is_risk_approved(decision) is True
        assert isinstance(decision, ApprovedOrderPlan)
        assert decision.volume > 0
        assert decision.stop_loss < decision.signal.entry_price
        assert decision.take_profit > decision.signal.entry_price
        assert decision.order_request.stop_loss == decision.stop_loss

    def test_position_size_not_hardcoded(self) -> None:
        decision = _manager().assess(
            make_buy_signal(),
            make_account(equity=50_000.0),
            make_xauusd_symbol(),
            [],
            make_risk_state(day_start_equity=50_000.0, peak_equity=50_000.0),
        )
        assert isinstance(decision, ApprovedOrderPlan)
        assert decision.volume != 0.1


class TestRiskManagerRejections:
    def test_hold_signal_rejected(self) -> None:
        signal = make_buy_signal()
        hold = signal.model_copy(update={"action": SignalAction.HOLD})
        decision = _manager().assess(hold, make_account(), make_xauusd_symbol(), [])
        assert is_risk_approved(decision) is False
        assert risk_rejection_reason(decision) == "HOLD signal — no action"

    def test_missing_account_rejected(self) -> None:
        decision = _manager().assess(make_buy_signal(), None, make_xauusd_symbol(), [])
        assert isinstance(decision, RejectedSignal)
        assert decision.reason == "Account information unavailable"

    def test_missing_symbol_rejected(self) -> None:
        decision = _manager().assess(make_buy_signal(), make_account(), None, [])
        assert decision.reason == "Symbol specification unavailable"

    def test_missing_atr_rejected(self) -> None:
        decision = _manager().assess(
            make_buy_signal(atr_14=None),
            make_account(),
            make_xauusd_symbol(),
            [],
        )
        assert "ATR14 unavailable" in decision.reason

    def test_daily_loss_rejected(self) -> None:
        decision = _manager().assess(
            make_buy_signal(),
            make_account(equity=9700.0),
            make_xauusd_symbol(),
            [],
            make_risk_state(day_start_equity=10_000.0),
        )
        assert decision.reason == "Maximum daily loss exceeded"

    def test_drawdown_rejected(self) -> None:
        decision = _manager().assess(
            make_buy_signal(),
            make_account(equity=9400.0),
            make_xauusd_symbol(),
            [],
            make_risk_state(day_start_equity=9400.0, peak_equity=10_000.0),
        )
        assert decision.reason == "Maximum drawdown exceeded"

    def test_spread_rejected(self) -> None:
        decision = _manager(MAX_SPREAD_POINTS=50).assess(
            make_buy_signal(),
            make_account(),
            make_xauusd_symbol(spread=100),
            [],
        )
        assert "Spread too wide" in decision.reason

    def test_max_open_positions_rejected(self) -> None:
        position = Position(
            ticket=1,
            symbol="XAUUSD",
            volume=0.01,
            direction=SignalDirection.LONG,
            open_price=2350.0,
            current_price=2351.0,
            open_time=datetime(2026, 1, 1, tzinfo=UTC),
        )
        decision = _manager(MAX_OPEN_POSITIONS=1).assess(
            make_buy_signal(),
            make_account(),
            make_xauusd_symbol(),
            [position],
        )
        assert "Maximum open positions" in decision.reason

    def test_max_position_size_rejected(self) -> None:
        decision = _manager(MAX_POSITION_LOTS=0.01).assess(
            make_buy_signal(),
            make_account(equity=100_000.0),
            make_xauusd_symbol(),
            [],
        )
        assert "exceeds maximum allowed" in decision.reason

    def test_insufficient_margin_rejected(self) -> None:
        decision = _manager().assess(
            make_buy_signal(),
            make_account(free_margin=1.0, leverage=500),
            make_xauusd_symbol(),
            [],
        )
        assert "Insufficient free margin" in decision.reason

    def test_volume_below_minimum_rejected(self) -> None:
        decision = _manager(RISK_PER_TRADE_PCT=0.01).assess(
            make_buy_signal(),
            make_account(equity=100.0),
            make_xauusd_symbol(),
            [],
        )
        assert "below minimum lot" in decision.reason


class TestRiskDecisionHelpers:
    def test_rejected_signal_action(self) -> None:
        decision = _manager().assess(make_buy_signal(), None, make_xauusd_symbol(), [])
        assert isinstance(decision, RejectedSignal)
        assert decision.action == TradeAction.REJECTED

    def test_boundary_daily_loss_exactly_at_limit(self) -> None:
        decision = _manager(MAX_DAILY_LOSS_PCT=2.0).assess(
            make_buy_signal(),
            make_account(equity=9800.0),
            make_xauusd_symbol(),
            [],
            make_risk_state(day_start_equity=10_000.0),
        )
        assert is_risk_approved(decision) is False
        assert decision.reason == "Maximum daily loss exceeded"

    def test_boundary_drawdown_exactly_at_limit(self) -> None:
        decision = _manager(MAX_DRAWDOWN_PCT=5.0).assess(
            make_buy_signal(),
            make_account(equity=9500.0),
            make_xauusd_symbol(),
            [],
            make_risk_state(day_start_equity=9500.0, peak_equity=10_000.0),
        )
        assert is_risk_approved(decision) is False
        assert decision.reason == "Maximum drawdown exceeded"
