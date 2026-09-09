"""Dashboard-aligned API response schemas (camelCase JSON)."""

from __future__ import annotations

from pydantic import Field

from exness_bot.api.schemas.common import ApiModel


class CandleEngineStatusDTO(ApiModel):
    status: str
    last_processed_at: str | None = Field(default=None, alias="lastProcessedAt")
    last_closed_at: str | None = Field(default=None, alias="lastClosedAt")
    last_update_at: str | None = Field(default=None, alias="lastUpdateAt")
    data_source: str = Field(alias="dataSource")


class SignalEngineStatusDTO(ApiModel):
    status: str
    strategy: str
    last_processed_candle: str | None = Field(default=None, alias="lastProcessedCandle")
    last_signal: str | None = Field(default=None, alias="lastSignal")
    last_signal_at: str | None = Field(default=None, alias="lastSignalAt")
    data_source: str = Field(alias="dataSource")


class PaperExecutionStatusDTO(ApiModel):
    status: str
    mode: str
    balance: float
    equity: float
    open_positions: int = Field(alias="openPositions")
    last_execution: str | None = Field(default=None, alias="lastExecution")
    last_execution_at: str | None = Field(default=None, alias="lastExecutionAt")
    session_id: str | None = Field(default=None, alias="sessionId")
    account_kind: str = Field(default="paper", alias="accountKind")


class PaperPositionDTO(ApiModel):
    position_id: str = Field(alias="positionId")
    symbol: str
    side: str
    volume: float
    entry_price: float = Field(alias="entryPrice")
    current_price: float = Field(alias="currentPrice")
    stop_loss: float | None = Field(default=None, alias="stopLoss")
    take_profit: float | None = Field(default=None, alias="takeProfit")
    unrealized_pnl: float = Field(alias="unrealizedPnl")
    opened_at: str = Field(alias="openedAt")
    status: str


class PaperTradeRowDTO(ApiModel):
    time: str
    symbol: str
    side: str
    volume: float
    entry: float | None = None
    stop_loss: float | None = Field(default=None, alias="stopLoss")
    take_profit: float | None = Field(default=None, alias="takeProfit")
    exit_price: float | None = Field(default=None, alias="exit")
    pnl: float | None = None
    status: str
    reason: str | None = None


class PaperTradingDTO(ApiModel):
    status: str
    mode: str
    research_only: bool = Field(alias="researchOnly")
    account_kind: str = Field(default="paper", alias="accountKind")
    session_id: str | None = Field(default=None, alias="sessionId")
    started_at: str | None = Field(default=None, alias="startedAt")
    initial_balance: float = Field(alias="initialBalance")
    balance: float
    equity: float
    realized_pnl: float = Field(alias="realizedPnl")
    unrealized_pnl: float = Field(alias="unrealizedPnl")
    daily_pnl: float = Field(alias="dailyPnl")
    drawdown_pct: float = Field(alias="drawdownPct")
    open_positions: int = Field(alias="openPositions")
    execution_count: int = Field(default=0, alias="executionCount")
    signal_count: int = Field(default=0, alias="signalCount")
    candles_processed: int = Field(default=0, alias="candlesProcessed")
    rejected_count: int = Field(default=0, alias="rejectedCount")
    last_execution: str | None = Field(default=None, alias="lastExecution")
    last_execution_at: str | None = Field(default=None, alias="lastExecutionAt")
    last_signal: str | None = Field(default=None, alias="lastSignal")
    positions: list[PaperPositionDTO] = Field(default_factory=list)
    trades: list[PaperTradeRowDTO]


class SessionContextDTO(ApiModel):
    trading_mode: str = Field(alias="tradingMode")
    connection_status: str = Field(alias="connectionStatus")
    account_label: str = Field(alias="accountLabel")
    bot_status: str = Field(alias="botStatus")
    account_profile: str = Field(alias="accountProfile")
    candle_engine: CandleEngineStatusDTO | None = Field(default=None, alias="candleEngine")
    signal_engine: SignalEngineStatusDTO | None = Field(default=None, alias="signalEngine")
    paper_execution: PaperExecutionStatusDTO | None = Field(default=None, alias="paperExecution")


class QuoteDTO(ApiModel):
    symbol: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    spread: float | None = None
    digits: int = 5
    available: bool = True
    updated_at: str = Field(alias="updatedAt")
    freshness: str = "LIVE"


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
    profit: float = 0.0
    leverage: int = 0
    margin_level: float | None = Field(default=None, alias="marginLevel")


class AccountSafetyDTO(ApiModel):
    """Status-only safety panel — no mutation controls."""

    trade_mode: str = Field(alias="tradeMode")
    server: str | None = None
    mt5_status: str = Field(alias="mt5Status")
    algo_trading: str = Field(alias="algoTrading")
    kill_switch: str = Field(alias="killSwitch")
    execution_mode: str = Field(alias="executionMode")


class AccountOverviewDTO(ApiModel):
    """Phase 15.X account overview — separate from legacy AccountSnapshotDTO."""

    status: str
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    free_margin: float | None = Field(default=None, alias="freeMargin")
    margin_level: float | None = Field(default=None, alias="marginLevel")
    currency: str | None = None
    unrealized_pnl: float | None = Field(default=None, alias="unrealizedPnl")
    realized_pnl_today: float | None = Field(default=None, alias="realizedPnlToday")
    total_pnl_today: float | None = Field(default=None, alias="totalPnlToday")
    daily_return_pct: float | None = Field(default=None, alias="dailyReturnPct")
    daily_return_available: bool = Field(default=False, alias="dailyReturnAvailable")
    open_positions_count: int = Field(default=0, alias="openPositionsCount")
    server: str | None = None
    trade_mode: str | None = Field(default=None, alias="tradeMode")
    login_masked: str | None = Field(default=None, alias="loginMasked")
    updated_at: str = Field(alias="updatedAt")
    age_seconds: float = Field(alias="ageSeconds")
    message: str | None = None
    safety: AccountSafetyDTO


class DailyRealizedPnlDTO(ApiModel):
    date: str
    realized_pnl: float = Field(alias="realizedPnl")


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
    swap: float = 0.0


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
    commission: float = 0.0
    swap: float = 0.0


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


class LiveGateResultDTO(ApiModel):
    name: str
    allowed: bool
    reason: str
    severity: str


class LiveReadinessDTO(ApiModel):
    """Read-only live enablement preflight — never means orders are executable."""

    allowed: bool
    configuration_preflight_ready: bool = Field(alias="configurationPreflightReady")
    execution_capability: bool = Field(alias="executionCapability")
    readiness_status: str = Field(alias="readinessStatus")
    message: str
    evaluated_at: str = Field(alias="evaluatedAt")
    unresolved_unknown_count: int = Field(alias="unresolvedUnknownCount")
    kill_switch_enabled: bool = Field(alias="killSwitchEnabled")
    legacy_run_allowed: bool = Field(alias="legacyRunAllowed")
    mt5_executor_implemented: bool = Field(alias="mt5ExecutorImplemented")
    blocking_reasons: list[str] = Field(alias="blockingReasons")
    gates: list[LiveGateResultDTO]


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


class AccountProfileDTO(ApiModel):
    id: str
    kind: str
    label: str
    configured: bool
    login: int | None = None
    server: str | None = None
    active: bool


class AccountSwitchStateDTO(ApiModel):
    active_profile: str = Field(alias="activeProfile")
    trading_mode: str = Field(alias="tradingMode")
    allow_live_trading: bool = Field(alias="allowLiveTrading")
    read_only: bool = Field(alias="readOnly")
    live_orders_enabled: bool = Field(alias="liveOrdersEnabled")
    profiles: list[AccountProfileDTO]
    note: str


class ActivateAccountRequest(ApiModel):
    profile: str


class ClosePositionRequest(ApiModel):
    """Xác nhận đóng một vị thế — bắt buộc confirm phrase."""

    confirm: str


class ClosePositionsBulkRequest(ApiModel):
    """Đóng nhiều vị thế hoặc đóng tất cả."""

    confirm: str
    position_ids: list[str] | None = Field(default=None, alias="positionIds")
    close_all: bool = Field(default=False, alias="closeAll")


class ClosePositionItemResultDTO(ApiModel):
    position_id: str = Field(alias="positionId")
    symbol: str
    success: bool
    dry_run: bool = Field(default=False, alias="dryRun")
    execution_price: float | None = Field(default=None, alias="executionPrice")
    volume: float | None = None
    error_message: str | None = Field(default=None, alias="errorMessage")


class ClosePositionsResultDTO(ApiModel):
    requested: int
    closed: int
    failed: int
    account_profile: str = Field(alias="accountProfile")
    results: list[ClosePositionItemResultDTO]


class AnalystChatRequest(ApiModel):
    """Phase 16.3.5 — analysis-only chat body (no market facts as truth)."""

    message: str
    session_id: str | None = Field(default=None, alias="sessionId")


class AutoDemoStatusDTO(ApiModel):
    """Phase 17.3 — read-only autonomous DEMO status (no secrets)."""

    enabled: bool
    default_enabled: bool = Field(alias="defaultEnabled")
    trading_env: str = Field(alias="tradingEnv")
    kill_switch: bool = Field(alias="killSwitch")
    demo_approval: bool = Field(alias="demoApproval")
    allowlist_configured: bool = Field(alias="allowlistConfigured")
    allowlist_match: bool = Field(alias="allowlistMatch")
    account_login_masked: str | None = Field(default=None, alias="accountLoginMasked")
    account_trade_mode: str | None = Field(default=None, alias="accountTradeMode")
    demo_verified: bool = Field(alias="demoVerified")
    symbol: str
    timeframe: str
    latest_closed_m15: str | None = Field(default=None, alias="latestClosedM15")
    last_decision_id: str | None = Field(default=None, alias="lastDecisionId")
    last_execution_state: str | None = Field(default=None, alias="lastExecutionState")
    last_blocked_reason: str | None = Field(default=None, alias="lastBlockedReason")
    last_signal: str | None = Field(default=None, alias="lastSignal")
    note: str


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


# --- Phase 16: Market Analysis / Trade Proposal (read-only) ---


class AnalysisReasonDTO(ApiModel):
    code: str
    passed: bool
    message: str


class AnalysisMarketDTO(ApiModel):
    bid: float | None = None
    ask: float | None = None
    spread_points: float | None = Field(default=None, alias="spreadPoints")
    quote_timestamp: str | None = Field(default=None, alias="quoteTimestamp")
    quote_age_seconds: float | None = Field(default=None, alias="quoteAgeSeconds")


class AnalysisIndicatorsDTO(ApiModel):
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    atr14: float | None = None
    close: float | None = None


class AnalysisTradePlanDTO(ApiModel):
    entry: float
    stop_loss: float = Field(alias="stopLoss")
    take_profit: float = Field(alias="takeProfit")
    risk_reward_ratio: float = Field(alias="riskRewardRatio")


class AnalysisSizingDTO(ApiModel):
    equity: float
    risk_percent: float = Field(alias="riskPercent")
    risk_budget_usd: float = Field(alias="riskBudgetUsd")
    raw_volume: float | None = Field(default=None, alias="rawVolume")
    normalized_volume: float | None = Field(default=None, alias="normalizedVolume")
    broker_min_volume: float | None = Field(default=None, alias="brokerMinVolume")
    broker_max_volume: float | None = Field(default=None, alias="brokerMaxVolume")
    broker_volume_step: float | None = Field(default=None, alias="brokerVolumeStep")
    estimated_risk_usd: float | None = Field(default=None, alias="estimatedRiskUsd")
    estimated_risk_pct: float | None = Field(default=None, alias="estimatedRiskPct")
    broker_executable: bool = Field(alias="brokerExecutable")
    risk_acceptable: bool = Field(alias="riskAcceptable")


class AnalysisStructureDTO(ApiModel):
    classification: str
    latest_swing_high: float | None = Field(default=None, alias="latestSwingHigh")
    latest_swing_low: float | None = Field(default=None, alias="latestSwingLow")
    sequence: list[str] = Field(default_factory=list)
    nearest_support: float | None = Field(default=None, alias="nearestSupport")
    nearest_resistance: float | None = Field(default=None, alias="nearestResistance")
    distance_to_support: float | None = Field(default=None, alias="distanceToSupport")
    distance_to_resistance: float | None = Field(
        default=None, alias="distanceToResistance"
    )
    distance_to_support_atr: float | None = Field(
        default=None, alias="distanceToSupportAtr"
    )
    distance_to_resistance_atr: float | None = Field(
        default=None, alias="distanceToResistanceAtr"
    )


class TradeAnalysisDTO(ApiModel):
    symbol: str
    broker_symbol: str = Field(alias="brokerSymbol")
    timeframe: str
    strategy: str = "ema_rsi_atr_v1"
    market: AnalysisMarketDTO
    indicators: AnalysisIndicatorsDTO
    regime: str
    signal: str
    execution_status: str = Field(alias="executionStatus")
    trade: AnalysisTradePlanDTO | None = None
    sizing: AnalysisSizingDTO | None = None
    reasons: list[AnalysisReasonDTO]
    blocking_reasons: list[AnalysisReasonDTO] = Field(alias="blockingReasons")
    candle_timestamp: str | None = Field(default=None, alias="candleTimestamp")
    generated_at: str = Field(alias="generatedAt")
    status: str
    # Phase 16.1 additive (optional for older clients)
    strategy_signal: str | None = Field(default=None, alias="strategySignal")
    context_assessment: str | None = Field(default=None, alias="contextAssessment")
    structure: AnalysisStructureDTO | None = None


# --- Phase 16.2 Multi-Timeframe Analysis ---


class MtfVolumeDTO(ApiModel):
    source: str
    current: float | None = None
    average: float | None = None
    ratio: float | None = None
    state: str


class MtfPatternDTO(ApiModel):
    type: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class MtfScoreDTO(ApiModel):
    trend_score: float = Field(alias="trendScore")
    structure_score: float = Field(alias="structureScore")
    momentum_score: float = Field(alias="momentumScore")
    location_score: float = Field(alias="locationScore")
    volume_score: float = Field(alias="volumeScore")
    total_score: float = Field(alias="totalScore")


class MtfTimeframeDTO(ApiModel):
    timeframe: str
    candle_timestamp: str | None = Field(default=None, alias="candleTimestamp")
    close: float | None = None
    trend: str
    signal: str
    confidence: float
    score: MtfScoreDTO | None = None
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    atr14: float | None = None
    macd: float | None = None
    macd_signal: float | None = Field(default=None, alias="macdSignal")
    macd_histogram: float | None = Field(default=None, alias="macdHistogram")
    macd_momentum: str = Field(alias="macdMomentum")
    structure_classification: str = Field(alias="structureClassification")
    sequence: list[str] = Field(default_factory=list)
    nearest_support: float | None = Field(default=None, alias="nearestSupport")
    nearest_resistance: float | None = Field(default=None, alias="nearestResistance")
    volume: MtfVolumeDTO
    pattern: MtfPatternDTO
    status: str
    reasons: list[AnalysisReasonDTO] = Field(default_factory=list)


class MtfTakeProfitDTO(ApiModel):
    level: int
    price: float
    allocation_pct: float = Field(alias="allocationPct")
    rr: float
    reason: str


class MtfSetupDTO(ApiModel):
    type: str
    state: str
    entry_type: str = Field(alias="entryType")
    entry_price: float | None = Field(default=None, alias="entryPrice")
    entry_zone_low: float | None = Field(default=None, alias="entryZoneLow")
    entry_zone_high: float | None = Field(default=None, alias="entryZoneHigh")
    entry_reason: str = Field(alias="entryReason")
    stop_loss: float | None = Field(default=None, alias="stopLoss")
    sl_reason: str = Field(alias="slReason")
    sl_distance: float | None = Field(default=None, alias="slDistance")
    sl_distance_atr: float | None = Field(default=None, alias="slDistanceAtr")
    take_profits: list[MtfTakeProfitDTO] = Field(default_factory=list, alias="takeProfits")
    distance_to_entry: float | None = Field(default=None, alias="distanceToEntry")


class MultiTimeframeAnalysisDTO(ApiModel):
    symbol: str
    broker_symbol: str = Field(alias="brokerSymbol")
    current_price: float | None = Field(default=None, alias="currentPrice")
    timeframes: dict[str, MtfTimeframeDTO]
    final_signal: str = Field(alias="finalSignal")
    confidence_score: float = Field(alias="confidenceScore")
    confidence_meaning: str = Field(alias="confidenceMeaning")
    trend: str
    structure_summary: str = Field(alias="structureSummary")
    key_supports: list[float] = Field(default_factory=list, alias="keySupports")
    key_resistances: list[float] = Field(default_factory=list, alias="keyResistances")
    setup: MtfSetupDTO | None = None
    sizing: AnalysisSizingDTO | None = None
    execution_assessment: str = Field(alias="executionAssessment")
    reasons: list[AnalysisReasonDTO] = Field(default_factory=list)
    warnings: list[AnalysisReasonDTO] = Field(default_factory=list)
    summary_vi: list[str] = Field(default_factory=list, alias="summaryVi")
    generated_at: str = Field(alias="generatedAt")
    freshness: str


# --- Phase 16.3 Execution Candidate (read-only) ---


class ExecutionCandidateTakeProfitDTO(ApiModel):
    level: int
    price: float
    allocation_pct: float = Field(alias="allocationPct")
    rr: float
    reason: str


class ExecutionCandidateDTO(ApiModel):
    candidate_id: str = Field(alias="candidateId")
    setup_id: str = Field(alias="setupId")
    analysis_fingerprint: str = Field(alias="analysisFingerprint")
    symbol: str
    broker_symbol: str = Field(alias="brokerSymbol")
    side: str
    entry: float
    stop_loss: float = Field(alias="stopLoss")
    take_profits: list[ExecutionCandidateTakeProfitDTO] = Field(
        default_factory=list, alias="takeProfits"
    )
    proposed_volume: float | None = Field(default=None, alias="proposedVolume")
    estimated_risk_usd: float | None = Field(default=None, alias="estimatedRiskUsd")
    estimated_risk_pct: float | None = Field(default=None, alias="estimatedRiskPct")
    broker_executable: bool = Field(alias="brokerExecutable")
    risk_acceptable: bool = Field(alias="riskAcceptable")
    created_at: str = Field(alias="createdAt")


class ExecutionCandidateStatusDTO(ApiModel):
    eligible: bool
    setup_state: str = Field(alias="setupState")
    setup_id: str | None = Field(default=None, alias="setupId")
    analysis_fingerprint: str | None = Field(
        default=None, alias="analysisFingerprint"
    )
    candidate: ExecutionCandidateDTO | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    strategy_id: str = Field(alias="strategyId")
    confidence_score: float | None = Field(default=None, alias="confidenceScore")
    confidence_meaning: str = Field(alias="confidenceMeaning")
    generated_at: str = Field(alias="generatedAt")
