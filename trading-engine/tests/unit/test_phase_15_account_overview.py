"""Unit tests for account overview PnL formulas (Phase 15.X)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from exness_bot.account_overview.freshness import AccountDataStatus, classify_account_data_status
from exness_bot.account_overview.pnl import (
    compute_daily_return_pct,
    deal_net_realized_pnl,
    group_realized_by_utc_day,
    mask_login,
    sum_realized_pnl_from_closed_trades,
    sum_realized_pnl_from_deals,
    sum_unrealized_pnl,
)
from exness_bot.data.models import ProviderConnectionStatus
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import ClosedTrade, Position


def _pos(profit: float) -> Position:
    return Position(
        ticket=1,
        symbol="XAUUSD",
        volume=0.01,
        direction=SignalDirection.LONG,
        open_price=100.0,
        current_price=101.0,
        stop_loss=None,
        take_profit=None,
        profit=profit,
        swap=0.0,
        open_time=datetime.now(tz=UTC),
    )


def _trade(net: float, closed_at: datetime) -> ClosedTrade:
    return ClosedTrade(
        id="t1",
        symbol="XAUUSD",
        strategy="ema_rsi_atr_v1",
        direction=SignalDirection.LONG,
        volume=0.01,
        entry_price=1.0,
        exit_price=1.0,
        gross_pnl=net,
        commission=0.0,
        swap=0.0,
        net_pnl=net,
        exit_reason="manual",
        closed_at=closed_at,
        r_multiple=None,
    )


class TestUnrealized:
    def test_single_position(self) -> None:
        assert sum_unrealized_pnl([_pos(0.13)]) == 0.13

    def test_multiple_positions_aggregate(self) -> None:
        assert sum_unrealized_pnl([_pos(0.10), _pos(-0.03), _pos(0.06)]) == 0.13

    def test_empty(self) -> None:
        assert sum_unrealized_pnl([]) == 0.0


class TestRealizedDeals:
    def test_profit_swap_commission_fee(self) -> None:
        deal = SimpleNamespace(
            type=0,
            time=datetime(2026, 9, 7, 12, tzinfo=UTC).timestamp(),
            profit=1.0,
            swap=-0.1,
            commission=-0.2,
            fee=-0.05,
        )
        assert deal_net_realized_pnl(deal) == pytest.approx(0.65)

    def test_sum_today_excludes_balance_and_other_days(self) -> None:
        start = datetime(2026, 9, 7, tzinfo=UTC)
        end = start + timedelta(days=1)
        deals = [
            SimpleNamespace(
                type=0,
                time=start.timestamp() + 3600,
                profit=1.0,
                swap=0.0,
                commission=-0.1,
                fee=0.0,
            ),
            SimpleNamespace(
                type=2,  # BALANCE
                time=start.timestamp() + 7200,
                profit=100.0,
                swap=0.0,
                commission=0.0,
                fee=0.0,
            ),
            SimpleNamespace(
                type=1,
                time=(start - timedelta(days=1)).timestamp(),
                profit=9.0,
                swap=0.0,
                commission=0.0,
                fee=0.0,
            ),
        ]
        assert sum_realized_pnl_from_deals(deals, start=start, end=end) == 0.9

    def test_no_deals_today_zero(self) -> None:
        start = datetime(2026, 9, 7, tzinfo=UTC)
        end = start + timedelta(days=1)
        assert sum_realized_pnl_from_deals([], start=start, end=end) == 0.0


class TestRealizedClosedTrades:
    def test_negative_and_tiny(self) -> None:
        start = datetime(2026, 9, 7, tzinfo=UTC)
        end = start + timedelta(days=1)
        trades = [
            _trade(-0.08, start + timedelta(hours=1)),
            _trade(0.03, start + timedelta(hours=2)),
        ]
        assert sum_realized_pnl_from_closed_trades(trades, start=start, end=end) == -0.05


class TestDailyReturn:
    def test_tiny_account(self) -> None:
        pct = compute_daily_return_pct(
            equity=10.63,
            total_pnl_today=0.05,
            balance_cashflow_today=0.0,
        )
        assert pct is not None
        assert abs(pct - (0.05 / 10.58 * 100)) < 1e-9

    def test_unavailable_when_cashflow_unknown(self) -> None:
        assert (
            compute_daily_return_pct(
                equity=10.5,
                total_pnl_today=0.1,
                balance_cashflow_today=None,
            )
            is None
        )

    def test_unavailable_when_deposit(self) -> None:
        assert (
            compute_daily_return_pct(
                equity=110.5,
                total_pnl_today=0.1,
                balance_cashflow_today=100.0,
            )
            is None
        )

    def test_unavailable_when_start_non_positive(self) -> None:
        assert (
            compute_daily_return_pct(
                equity=0.05,
                total_pnl_today=0.1,
                balance_cashflow_today=0.0,
            )
            is None
        )


class TestFreshness:
    def test_disconnected(self) -> None:
        assert (
            classify_account_data_status(
                connection_status=ProviderConnectionStatus.DISCONNECTED,
                account_present=False,
                updated_at=datetime.now(tz=UTC),
            )
            == AccountDataStatus.DISCONNECTED
        )

    def test_unavailable(self) -> None:
        assert (
            classify_account_data_status(
                connection_status=ProviderConnectionStatus.ERROR,
                account_present=False,
                updated_at=datetime.now(tz=UTC),
            )
            == AccountDataStatus.UNAVAILABLE
        )

    def test_stale(self) -> None:
        now = datetime.now(tz=UTC)
        assert (
            classify_account_data_status(
                connection_status=ProviderConnectionStatus.CONNECTED,
                account_present=True,
                updated_at=now - timedelta(seconds=30),
                now=now,
                stale_after_seconds=10,
            )
            == AccountDataStatus.STALE
        )

    def test_live(self) -> None:
        now = datetime.now(tz=UTC)
        assert (
            classify_account_data_status(
                connection_status=ProviderConnectionStatus.CONNECTED,
                account_present=True,
                updated_at=now - timedelta(seconds=2),
                now=now,
                stale_after_seconds=10,
            )
            == AccountDataStatus.LIVE
        )


class TestMaskAndHistory:
    def test_mask_login(self) -> None:
        assert mask_login(1234158) == "***4158"
        assert mask_login(None) is None

    def test_group_realized_history(self) -> None:
        end = datetime(2026, 9, 7, 18, tzinfo=UTC)
        trades = [
            _trade(0.11, datetime(2026, 9, 1, 10, tzinfo=UTC)),
            _trade(-0.02, datetime(2026, 9, 7, 10, tzinfo=UTC)),
        ]
        rows = group_realized_by_utc_day(trades, days=7, end=end)
        assert len(rows) == 7
        assert rows[0][0] == "2026-09-01"
        assert rows[0][1] == 0.11
        assert rows[-1] == ("2026-09-07", -0.02)
