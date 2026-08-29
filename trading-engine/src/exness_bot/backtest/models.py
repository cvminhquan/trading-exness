"""Backtest domain models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from exness_bot.backtest.config import BacktestAssumptions, BacktestConfig
from exness_bot.domain.enums import SignalDirection


class ExitReason(StrEnum):
    """Why a simulated position was closed."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"


class SimulatedPosition(BaseModel):
    """Open virtual position during backtest."""

    direction: SignalDirection
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    entry_bar_index: int

    model_config = {"frozen": True}


class TradeRecord(BaseModel):
    """Completed round-trip trade in the journal."""

    trade_id: int
    direction: SignalDirection
    volume: float
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: ExitReason
    gross_pnl: float
    commission: float
    net_pnl: float
    bars_held: int
    signal_reason: str

    model_config = {"frozen": True}


class EquityPoint(BaseModel):
    """Equity snapshot on a bar close."""

    timestamp: datetime
    equity: float
    bar_index: int

    model_config = {"frozen": True}


class BacktestMetrics(BaseModel):
    """Aggregate performance statistics."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float | None
    expectancy: float
    maximum_drawdown: float
    maximum_drawdown_pct: float
    average_win: float
    average_loss: float
    risk_reward: float | None
    max_consecutive_wins: int
    max_consecutive_losses: int
    initial_equity: float
    final_equity: float
    return_pct: float

    model_config = {"frozen": True}


class BacktestReport(BaseModel):
    """Machine-readable backtest output."""

    strategy_name: str
    symbol: str
    timeframe: str
    config: BacktestConfig
    assumptions: BacktestAssumptions
    metrics: BacktestMetrics
    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]
    bars_processed: int
    signals_generated: int
    orders_approved: int
    orders_rejected: int

    model_config = {"frozen": True}
