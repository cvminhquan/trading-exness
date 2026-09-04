"""Paper execution domain models — virtual only, no broker tickets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.contract import IntentRecord


class ExecutionMode(StrEnum):
    PAPER = "paper"


class OrderStatus(StrEnum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PaperExitReason(StrEnum):
    SL = "SL"
    TP = "TP"
    MANUAL = "MANUAL"
    END_OF_SESSION = "END_OF_SESSION"
    RISK_LIMIT = "RISK_LIMIT"


class ExecutionOutcome(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    IGNORED = "IGNORED"
    DUPLICATE = "DUPLICATE"
    IN_FLIGHT = "IN_FLIGHT"
    UNKNOWN = "UNKNOWN"
    ACCEPTED = "ACCEPTED"
    CATCHUP_IGNORED = "CATCHUP_IGNORED"


class RejectionCode(StrEnum):
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    POSITION_SIZE_LIMIT = "POSITION_SIZE_LIMIT"
    INVALID_RISK = "INVALID_RISK"
    INVALID_SL = "INVALID_SL"
    INVALID_QUOTE = "INVALID_QUOTE"
    INVALID_VOLUME = "INVALID_VOLUME"
    INVALID_STOPS = "INVALID_STOPS"
    INVALID_TP = "INVALID_TP"


@dataclass(frozen=True)
class VirtualOrder:
    order_id: str
    signal_id: str
    symbol: str
    side: SignalDirection
    requested_price: float
    fill_price: float
    volume: float
    stop_loss: float
    take_profit: float
    created_at: datetime
    status: OrderStatus


@dataclass(frozen=True)
class VirtualPosition:
    position_id: str
    symbol: str
    side: SignalDirection
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    signal_id: str
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    current_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    last_calendar_day: datetime | None = None


@dataclass(frozen=True)
class VirtualExit:
    position_id: str
    symbol: str
    side: SignalDirection
    volume: float
    entry_price: float
    exit_price: float
    exit_timestamp: datetime
    exit_reason: PaperExitReason
    gross_pnl: float
    commission: float
    swap: float
    net_pnl: float
    signal_id: str


@dataclass(frozen=True)
class PaperRejection:
    signal_id: str
    code: RejectionCode
    reason: str
    at: datetime


@dataclass(frozen=True)
class PaperAccount:
    initial_balance: float
    balance: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    daily_pnl: float
    drawdown_pct: float
    peak_equity: float
    day_start_equity: float
    mode: str = ExecutionMode.PAPER.value


@dataclass(frozen=True)
class ConsumeResult:
    status: ExecutionOutcome
    order: VirtualOrder | None = None
    position: VirtualPosition | None = None
    rejection_code: RejectionCode | None = None
    reason: str = ""


@dataclass(frozen=True)
class PaperSession:
    session_id: str
    started_at: datetime | None
    initial_balance: float
    balance: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown_pct: float
    daily_pnl: float
    open_positions: int
    execution_count: int
    signal_count: int
    candles_processed: int
    rejected_count: int
    mode: str = ExecutionMode.PAPER.value


@dataclass
class PaperSnapshot:
    initial_balance: float
    cash_balance: float
    realized_pnl: float
    peak_equity: float
    day_start_equity: float
    executed_keys: tuple[str, ...] = ()
    positions: tuple[VirtualPosition, ...] = ()
    orders: tuple[VirtualOrder, ...] = ()
    exits: tuple[VirtualExit, ...] = ()
    rejections: tuple[PaperRejection, ...] = ()
    intents: tuple[IntentRecord, ...] = ()
    next_id: int = 1
    accumulated_swap: float = 0.0
    session_id: str = ""
    started_at: datetime | None = None
    candles_processed: int = 0
    signal_count: int = 0

    @classmethod
    def initial(cls, balance: float) -> PaperSnapshot:
        return cls(
            initial_balance=balance,
            cash_balance=balance,
            realized_pnl=0.0,
            peak_equity=balance,
            day_start_equity=balance,
            session_id=str(uuid4()),
            started_at=datetime.now(tz=UTC),
        )

    def with_balances(
        self,
        *,
        cash_balance: float,
        peak_equity: float,
        day_start_equity: float,
    ) -> PaperSnapshot:
        return replace(
            self,
            cash_balance=cash_balance,
            peak_equity=peak_equity,
            day_start_equity=day_start_equity,
            realized_pnl=round(cash_balance - self.initial_balance, 2),
        )
