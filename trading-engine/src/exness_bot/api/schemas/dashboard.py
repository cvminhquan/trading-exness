"""Dashboard-aligned API response schemas (camelCase JSON)."""

from __future__ import annotations

from pydantic import Field

from exness_bot.api.schemas.common import ApiModel


class SessionContextDTO(ApiModel):
    trading_mode: str = Field(alias="tradingMode")
    connection_status: str = Field(alias="connectionStatus")
    account_label: str = Field(alias="accountLabel")
    bot_status: str = Field(alias="botStatus")


class AccountSnapshotDTO(ApiModel):
    balance: float
    equity: float
    today_pnl: float = Field(alias="todayPnl")
    total_pnl: float = Field(alias="totalPnl")
    drawdown_pct: float = Field(alias="drawdownPct")
    margin: float
    free_margin: float = Field(alias="freeMargin")
    currency: str = "USD"
    updated_at: str = Field(alias="updatedAt")


class EquityPointDTO(ApiModel):
    timestamp: str
    equity: float


class PositionDTO(ApiModel):
    id: str
    symbol: str
    direction: str
    volume: float
    entry_price: float = Field(alias="entryPrice")
    current_price: float = Field(alias="currentPrice")
    stop_loss: float | None = Field(alias="stopLoss")
    take_profit: float | None = Field(alias="takeProfit")
    unrealized_pnl: float = Field(alias="unrealizedPnl")
    r_multiple: float | None = Field(alias="rMultiple")
    opened_at: str = Field(alias="openedAt")


class TradeDTO(ApiModel):
    id: str
    closed_at: str = Field(alias="closedAt")
    symbol: str
    strategy: str
    direction: str
    entry_price: float = Field(alias="entryPrice")
    exit_price: float = Field(alias="exitPrice")
    volume: float
    gross_pnl: float = Field(alias="grossPnl")
    costs: float
    net_pnl: float = Field(alias="netPnl")
    r_multiple: float | None = Field(alias="rMultiple")
    exit_reason: str = Field(alias="exitReason")


class IndicatorSnapshotDTO(ApiModel):
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    atr14: float | None = None


class SignalConditionDTO(ApiModel):
    id: str
    label: str
    detail: str
    satisfied: bool


class StrategySignalDTO(ApiModel):
    symbol: str
    strategy: str
    action: str
    direction: str
    timestamp: str
    indicators: IndicatorSnapshotDTO
    reason: str
    conditions: list[SignalConditionDTO]
    summary: str


class StrategySnapshotDTO(ApiModel):
    id: str
    name: str
    symbol: str
    timeframe: str
    status: str
    current_signal: StrategySignalDTO = Field(alias="currentSignal")
    recent_signals: list[StrategySignalDTO] = Field(alias="recentSignals")


class RiskLimitDTO(ApiModel):
    key: str
    label: str
    category: str
    configured_limit: float = Field(alias="configuredLimit")
    current_value: float = Field(alias="currentValue")
    unit: str


class RiskSnapshotDTO(ApiModel):
    equity: float
    risk_per_trade_pct: float = Field(alias="riskPerTradePct")
    limits: list[RiskLimitDTO]
    updated_at: str = Field(alias="updatedAt")


class SystemSettingsDTO(ApiModel):
    trading_mode: str = Field(alias="tradingMode")
    broker: str
    symbol: str
    timeframe: str
    strategy: str
    risk_per_trade_pct: float = Field(alias="riskPerTradePct")
    max_daily_loss_pct: float = Field(alias="maxDailyLossPct")
    max_drawdown_pct: float = Field(alias="maxDrawdownPct")
    max_open_positions: int = Field(alias="maxOpenPositions")


class DashboardOverviewDTO(ApiModel):
    bot_status: str = Field(alias="botStatus")
    account: AccountSnapshotDTO
    equity_curve: list[EquityPointDTO] = Field(alias="equityCurve")
    positions: list[PositionDTO]
    recent_trades: list[TradeDTO] = Field(alias="recentTrades")
    current_signal: StrategySignalDTO = Field(alias="currentSignal")


class BacktestDatasetDTO(ApiModel):
    total_candles: int = Field(alias="totalCandles")
    start_timestamp: str | None = Field(alias="startTimestamp")
    end_timestamp: str | None = Field(alias="endTimestamp")
    duration_days: float = Field(alias="durationDays")
    timezone: str
    duplicate_timestamps: int = Field(alias="duplicateTimestamps")
    missing_periods: int = Field(alias="missingPeriods")
    missing_bars_total: int = Field(alias="missingBarsTotal")
    weekend_gaps: int = Field(alias="weekendGaps")
    session_gaps: int = Field(alias="sessionGaps")
    is_sorted: bool = Field(alias="isSorted")
    is_valid_ohlc: bool = Field(alias="isValidOhlc")
    is_meaningful: bool = Field(alias="isMeaningful")
    min_required_candles: int = Field(alias="minRequiredCandles")
    recommended_candles: int = Field(alias="recommendedCandles")
    quality_status: str = Field(alias="qualityStatus")


class BacktestExecutionConfigDTO(ApiModel):
    initial_balance: float = Field(alias="initialBalance")
    risk_per_trade_pct: float = Field(alias="riskPerTradePct")
    max_daily_loss_pct: float = Field(alias="maxDailyLossPct")
    max_drawdown_pct: float = Field(alias="maxDrawdownPct")
    max_open_positions: int = Field(alias="maxOpenPositions")
    max_position_lots: float = Field(alias="maxPositionLots")
    spread_points: int = Field(alias="spreadPoints")
    slippage_points: float = Field(alias="slippagePoints")
    commission_per_lot: float = Field(alias="commissionPerLot")
    swap_per_lot_per_day: float = Field(alias="swapPerLotPerDay")
    warmup_bars: int = Field(alias="warmupBars")


class BacktestAssumptionsDTO(ApiModel):
    candle_timing: str = Field(alias="candleTiming")
    execution: str
    spread: str
    slippage: str
    commission: str
    swap: str
    exit_costs: str = Field(alias="exitCosts")
    position_limit: str = Field(alias="positionLimit")
    end_of_data: str = Field(alias="endOfData")
    position_sizing: str = Field(alias="positionSizing")
    same_bar_exit_rule: str = Field(alias="sameBarExitRule")


class BacktestPerformanceDTO(ApiModel):
    total_trades: int = Field(alias="totalTrades")
    winning_trades: int = Field(alias="winningTrades")
    losing_trades: int = Field(alias="losingTrades")
    win_rate: float = Field(alias="winRate")
    gross_profit: float = Field(alias="grossProfit")
    gross_loss: float = Field(alias="grossLoss")
    net_profit: float = Field(alias="netProfit")
    total_commission: float = Field(alias="totalCommission")
    total_swap: float = Field(alias="totalSwap")
    profit_factor: float | None = Field(alias="profitFactor")
    expectancy: float
    average_win: float = Field(alias="averageWin")
    average_loss: float = Field(alias="averageLoss")
    average_trade: float | None = Field(alias="averageTrade")
    average_r: float | None = Field(alias="averageR")
    largest_win: float | None = Field(alias="largestWin")
    largest_loss: float | None = Field(alias="largestLoss")
    max_consecutive_wins: int = Field(alias="maxConsecutiveWins")
    max_consecutive_losses: int = Field(alias="maxConsecutiveLosses")
    initial_balance: float = Field(alias="initialBalance")
    final_balance: float = Field(alias="finalBalance")
    return_pct: float = Field(alias="returnPct")
    max_drawdown_pct: float = Field(alias="maxDrawdownPct")
    max_drawdown_usd: float = Field(alias="maxDrawdownUsd")
    max_drawdown_duration_bars: int | None = Field(alias="maxDrawdownDurationBars")
    current_drawdown_pct: float | None = Field(alias="currentDrawdownPct")
    average_trade_duration_bars: int | None = Field(alias="averageTradeDurationBars")


class BacktestTradeRecordDTO(ApiModel):
    trade_id: int = Field(alias="tradeId")
    direction: str
    volume: float
    entry_price: float = Field(alias="entryPrice")
    exit_price: float = Field(alias="exitPrice")
    stop_loss: float = Field(alias="stopLoss")
    take_profit: float = Field(alias="takeProfit")
    entry_time: str = Field(alias="entryTime")
    exit_time: str = Field(alias="exitTime")
    exit_reason: str = Field(alias="exitReason")
    gross_pnl: float = Field(alias="grossPnl")
    commission: float
    swap: float
    net_pnl: float = Field(alias="netPnl")
    bars_held: int = Field(alias="barsHeld")
    r_multiple: float | None = Field(alias="rMultiple")
    signal_reason: str = Field(alias="signalReason")


class MonthlyPerformanceDTO(ApiModel):
    month: str
    net_pnl: float = Field(alias="netPnl")
    return_pct: float | None = Field(alias="returnPct")
    trades: int
    win_rate: float = Field(alias="winRate")


class BacktestRAnalysisDTO(ApiModel):
    average_r: float | None = Field(alias="averageR")
    winning_r_average: float | None = Field(alias="winningRAverage")
    losing_r_average: float | None = Field(alias="losingRAverage")
    best_r: float | None = Field(alias="bestR")
    worst_r: float | None = Field(alias="worstR")
    r_multiples: list[float] = Field(alias="rMultiples")


class BacktestClassificationDTO(ApiModel):
    classification: str
    rationale: list[str]


class BacktestReportDTO(ApiModel):
    id: str
    strategy: str
    symbol: str
    timeframe: str
    status: str
    generated_at: str = Field(alias="generatedAt")
    message: str | None
    period_start: str | None = Field(alias="periodStart")
    period_end: str | None = Field(alias="periodEnd")
    dataset: BacktestDatasetDTO | None
    execution: BacktestExecutionConfigDTO | None
    performance: BacktestPerformanceDTO | None
    assumptions: BacktestAssumptionsDTO | None
    classification: BacktestClassificationDTO | None
    equity_curve: list[EquityPointDTO] = Field(alias="equityCurve")
    drawdown_curve: list[EquityPointDTO] = Field(alias="drawdownCurve")
    trades: list[BacktestTradeRecordDTO]
    monthly_performance: list[MonthlyPerformanceDTO] = Field(alias="monthlyPerformance")
    r_analysis: BacktestRAnalysisDTO | None = Field(alias="rAnalysis")
