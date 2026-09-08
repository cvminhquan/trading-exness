"""Pure PnL formulas for account overview (read-only).

Realized NET (per MT5 deal / closed trade):
    profit + swap + commission + fee

Only BUY/SELL trading deals are included (balance/credit excluded).
Entry deals typically contribute commission/fee with profit≈0; exit deals
carry floating→realized profit — summing all trading deals in the window
does not double-count profit.

Unrealized:
    sum(position.profit for open positions)

Daily return (when trusted):
    daily_start_equity = equity - total_pnl_today
    daily_return_pct = total_pnl_today / daily_start_equity * 100
Unavailable when start equity ≤ 0 or non-trading cashflow today ≠ 0.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

# MetaTrader5 DEAL_TYPE_* (trading only)
MT5_DEAL_TYPE_BUY = 0
MT5_DEAL_TYPE_SELL = 1
MT5_DEAL_TYPE_BALANCE = 2
MT5_DEAL_TYPE_CREDIT = 3


def deal_net_realized_pnl(deal: Any) -> float:
    """NET realized contribution of one MT5 deal (not rounded)."""
    profit = float(getattr(deal, "profit", 0.0) or 0.0)
    swap = float(getattr(deal, "swap", 0.0) or 0.0)
    commission = float(getattr(deal, "commission", 0.0) or 0.0)
    fee = float(getattr(deal, "fee", 0.0) or 0.0)
    return profit + swap + commission + fee


def is_trading_deal(deal: Any) -> bool:
    deal_type = int(getattr(deal, "type", -1))
    return deal_type in (MT5_DEAL_TYPE_BUY, MT5_DEAL_TYPE_SELL)


def is_balance_cashflow_deal(deal: Any) -> bool:
    deal_type = int(getattr(deal, "type", -1))
    return deal_type in (MT5_DEAL_TYPE_BALANCE, MT5_DEAL_TYPE_CREDIT)


def _deal_time(deal: Any) -> datetime | None:
    raw = getattr(deal, "time", None)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def sum_realized_pnl_from_deals(
    deals: Iterable[Any],
    *,
    start: datetime,
    end: datetime,
) -> float:
    """Sum NET realized PnL from BUY/SELL deals in [start, end)."""
    total = 0.0
    for deal in deals:
        if not is_trading_deal(deal):
            continue
        when = _deal_time(deal)
        if when is None or when < start or when >= end:
            continue
        total += deal_net_realized_pnl(deal)
    return total


def sum_balance_cashflow_from_deals(
    deals: Iterable[Any],
    *,
    start: datetime,
    end: datetime,
) -> float:
    """Sum deposit/withdrawal-style cashflow (BALANCE/CREDIT) in [start, end)."""
    total = 0.0
    for deal in deals:
        if not is_balance_cashflow_deal(deal):
            continue
        when = _deal_time(deal)
        if when is None or when < start or when >= end:
            continue
        total += float(getattr(deal, "profit", 0.0) or 0.0)
    return total


def sum_realized_pnl_from_closed_trades(
    trades: Iterable[Any],
    *,
    start: datetime,
    end: datetime,
) -> float:
    """Sum ClosedTrade.net_pnl for exits in [start, end)."""
    total = 0.0
    for trade in trades:
        closed = trade.closed_at
        aware = closed if closed.tzinfo is not None else closed.replace(tzinfo=UTC)
        if aware < start or aware >= end:
            continue
        total += float(trade.net_pnl)
    return total


def sum_unrealized_pnl(positions: Iterable[Any]) -> float:
    return sum(float(getattr(position, "profit", 0.0) or 0.0) for position in positions)


def compute_daily_return_pct(
    *,
    equity: float,
    total_pnl_today: float,
    balance_cashflow_today: float | None,
) -> float | None:
    """Return daily return % or None when the denominator is not trustworthy."""
    if balance_cashflow_today is None:
        return None
    if abs(balance_cashflow_today) > 1e-9:
        return None
    daily_start_equity = equity - total_pnl_today
    if daily_start_equity <= 0:
        return None
    return (total_pnl_today / daily_start_equity) * 100.0


def utc_day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """UTC midnight containing `moment` → [start, next_day)."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    aware = aware.astimezone(UTC)
    start = datetime(aware.year, aware.month, aware.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def utc_date_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def mask_login(login: int | None) -> str | None:
    if login is None:
        return None
    text = str(abs(int(login)))
    if len(text) <= 4:
        return f"***{text}"
    return f"***{text[-4:]}"


def group_realized_by_utc_day(
    trades: Iterable[Any],
    *,
    days: int,
    end: datetime,
) -> list[tuple[str, float]]:
    """Build chronological list of (YYYY-MM-DD, realizedPnl) for the last `days` UTC days."""
    aware_end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
    aware_end = aware_end.astimezone(UTC)
    end_day = aware_end.date()
    start_day = end_day - timedelta(days=days - 1)
    buckets: dict[str, float] = {}
    cursor = start_day
    while cursor <= end_day:
        buckets[cursor.isoformat()] = 0.0
        cursor += timedelta(days=1)

    range_start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
    range_end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=UTC) + timedelta(days=1)
    for trade in trades:
        closed = trade.closed_at
        aware = closed if closed.tzinfo is not None else closed.replace(tzinfo=UTC)
        aware = aware.astimezone(UTC)
        if aware < range_start or aware >= range_end:
            continue
        key = aware.date().isoformat()
        if key in buckets:
            buckets[key] += float(trade.net_pnl)

    return [(key, buckets[key]) for key in sorted(buckets)]
