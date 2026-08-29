"""Core domain models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from exness_bot.domain.enums import OrderType, SignalAction, SignalDirection, Timeframe, TradeAction

ACTION_TO_DIRECTION: dict[SignalAction, SignalDirection] = {
    SignalAction.BUY: SignalDirection.LONG,
    SignalAction.SELL: SignalDirection.SHORT,
    SignalAction.HOLD: SignalDirection.FLAT,
}


class Bar(BaseModel):
    """Single OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    model_config = {"frozen": True}


class IndicatorSnapshot(BaseModel):
    """Computed indicator values at a point in time."""

    timestamp: datetime
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None

    model_config = {"frozen": True}


class Signal(BaseModel):
    """Trading signal produced by a strategy."""

    action: SignalAction
    strategy_name: str
    symbol: str
    timeframe: Timeframe
    direction: SignalDirection
    entry_price: float
    timestamp: datetime
    indicators: IndicatorSnapshot
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}

    @classmethod
    def create(
        cls,
        *,
        action: SignalAction,
        strategy_name: str,
        symbol: str,
        timeframe: Timeframe,
        entry_price: float,
        timestamp: datetime,
        indicators: IndicatorSnapshot,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Signal":
        """Create a signal with direction derived from action."""
        return cls(
            action=action,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            direction=ACTION_TO_DIRECTION[action],
            entry_price=entry_price,
            timestamp=timestamp,
            indicators=indicators,
            reason=reason,
            metadata=metadata or {},
        )


class AccountInfo(BaseModel):
    """Broker account information."""

    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str = "USD"
    leverage: int = 0
    name: str = ""
    server: str = ""
    trade_mode: str = "demo"

    model_config = {"frozen": True}


class SymbolInfo(BaseModel):
    """Broker symbol specification."""

    symbol: str
    bid: float
    ask: float
    point: float
    digits: int
    volume_min: float
    volume_max: float
    volume_step: float
    trade_contract_size: float
    spread: int
    trade_mode: int
    visible: bool

    model_config = {"frozen": True}


class Tick(BaseModel):
    """Latest price tick for a symbol."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime

    model_config = {"frozen": True}


class Candle(BaseModel):
    """Historical OHLCV candle."""

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: int | None = None

    model_config = {"frozen": True}


class PendingOrder(BaseModel):
    """Pending (non-filled) order."""

    ticket: int
    symbol: str
    order_type: OrderType
    direction: SignalDirection
    volume: float
    price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    setup_time: datetime
    comment: str = ""

    model_config = {"frozen": True}


class HealthStatus(BaseModel):
    """Broker connection health snapshot."""

    connected: bool
    terminal_connected: bool
    trade_allowed: bool
    account_login: int | None = None
    server: str | None = None
    message: str = ""

    model_config = {"frozen": True}


class Position(BaseModel):
    """Open trading position."""

    ticket: int
    symbol: str
    volume: float
    direction: SignalDirection
    open_price: float
    current_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    profit: float = 0.0
    swap: float = 0.0
    open_time: datetime

    model_config = {"frozen": True}


class ClosedTrade(BaseModel):
    """Completed round-trip trade from broker history."""

    id: str
    symbol: str
    strategy: str
    direction: SignalDirection
    volume: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    commission: float
    swap: float
    net_pnl: float
    exit_reason: str
    closed_at: datetime
    r_multiple: float | None = None

    model_config = {"frozen": True}


class OrderRequest(BaseModel):
    """Request to place an order via broker."""

    symbol: str
    volume: float
    order_type: OrderType
    direction: SignalDirection
    stop_loss: float | None = None
    take_profit: float | None = None
    comment: str = "exness-bot"
    deviation: int = 20

    model_config = {"frozen": True}


class OrderResult(BaseModel):
    """Result of an order submission with execution details."""

    success: bool
    ticket: int | None = None
    execution_price: float | None = None
    volume: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    timestamp: datetime | None = None
    error_code: int | None = None
    error_message: str | None = None
    dry_run: bool = False
    reconciled: bool = False
    reconciliation_message: str | None = None

    model_config = {"frozen": True}


class ApprovedOrderPlan(BaseModel):
    """Risk-approved order plan ready for execution."""

    signal: Signal
    volume: float
    stop_loss: float
    take_profit: float
    order_request: OrderRequest

    model_config = {"frozen": True}


class RejectedSignal(BaseModel):
    """Signal rejected by risk manager."""

    signal: Signal
    reason: str
    action: TradeAction = TradeAction.REJECTED

    model_config = {"frozen": True}


RiskDecision = ApprovedOrderPlan | RejectedSignal
