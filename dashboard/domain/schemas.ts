import { z } from "zod";

export const botStatusSchema = z.enum(["RUNNING", "STOPPED", "ERROR", "DISCONNECTED"]);
export type BotStatus = z.infer<typeof botStatusSchema>;

export const directionSchema = z.enum(["LONG", "SHORT", "FLAT"]);
export type Direction = z.infer<typeof directionSchema>;

export const signalActionSchema = z.enum(["BUY", "SELL", "HOLD", "NO_SIGNAL", "INVALID"]);
export type SignalAction = z.infer<typeof signalActionSchema>;

export const exitReasonSchema = z.enum(["stop_loss", "take_profit", "end_of_data", "manual"]);
export type ExitReason = z.infer<typeof exitReasonSchema>;

export const accountSnapshotSchema = z.object({
  balance: z.number(),
  equity: z.number(),
  todayPnl: z.number(),
  totalPnl: z.number(),
  drawdownPct: z.number(),
  margin: z.number(),
  freeMargin: z.number(),
    currency: z.string().default("USD"),
  updatedAt: z.string().datetime(),
  profit: z.number().default(0),
  leverage: z.number().int().default(0),
  marginLevel: z.number().nullable().default(null),
});
export type AccountSnapshot = z.infer<typeof accountSnapshotSchema>;

export const accountDataStatusSchema = z.enum([
  "LIVE",
  "STALE",
  "DISCONNECTED",
  "UNAVAILABLE",
]);
export type AccountDataStatus = z.infer<typeof accountDataStatusSchema>;

export const accountSafetySchema = z.object({
  tradeMode: z.string(),
  server: z.string().nullable(),
  mt5Status: z.enum(["CONNECTED", "DISCONNECTED"]),
  algoTrading: z.enum(["ENABLED", "DISABLED", "UNKNOWN"]),
  killSwitch: z.enum(["ON", "OFF"]),
  executionMode: z.enum(["PAPER", "LIVE"]),
});
export type AccountSafety = z.infer<typeof accountSafetySchema>;

export const accountOverviewSchema = z.object({
  status: accountDataStatusSchema,
  balance: z.number().nullable().optional(),
  equity: z.number().nullable().optional(),
  margin: z.number().nullable().optional(),
  freeMargin: z.number().nullable().optional(),
  marginLevel: z.number().nullable().optional(),
  currency: z.string().nullable().optional(),
  unrealizedPnl: z.number().nullable().optional(),
  realizedPnlToday: z.number().nullable().optional(),
  totalPnlToday: z.number().nullable().optional(),
  dailyReturnPct: z.number().nullable().optional(),
  dailyReturnAvailable: z.boolean().default(false),
  openPositionsCount: z.number().int().default(0),
  server: z.string().nullable().optional(),
  tradeMode: z.string().nullable().optional(),
  loginMasked: z.string().nullable().optional(),
  updatedAt: z.string().datetime(),
  ageSeconds: z.number(),
  message: z.string().nullable().optional(),
  safety: accountSafetySchema,
});
export type AccountOverview = z.infer<typeof accountOverviewSchema>;

export const dailyRealizedPnlSchema = z.object({
  date: z.string(),
  realizedPnl: z.number(),
});
export type DailyRealizedPnl = z.infer<typeof dailyRealizedPnlSchema>;

export const equityPointSchema = z.object({
  timestamp: z.string().datetime(),
  equity: z.number(),
});
export type EquityPoint = z.infer<typeof equityPointSchema>;

export const positionSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  direction: directionSchema,
  volume: z.number(),
  entryPrice: z.number(),
  currentPrice: z.number(),
  stopLoss: z.number().nullable(),
  takeProfit: z.number().nullable(),
  unrealizedPnl: z.number(),
  rMultiple: z.number().nullable(),
  openedAt: z.string().datetime(),
  swap: z.number().default(0),
});
export type Position = z.infer<typeof positionSchema>;

export const closePositionItemResultSchema = z.object({
  positionId: z.string(),
  symbol: z.string(),
  success: z.boolean(),
  dryRun: z.boolean().default(false),
  executionPrice: z.number().nullable().optional(),
  volume: z.number().nullable().optional(),
  errorMessage: z.string().nullable().optional(),
});

export const closePositionsResultSchema = z.object({
  requested: z.number(),
  closed: z.number(),
  failed: z.number(),
  accountProfile: z.string(),
  results: z.array(closePositionItemResultSchema),
});
export type ClosePositionsResult = z.infer<typeof closePositionsResultSchema>;

export const tradeSchema = z.object({
  id: z.string(),
  closedAt: z.string().datetime(),
  symbol: z.string(),
  strategy: z.string(),
  direction: directionSchema,
  entryPrice: z.number(),
  exitPrice: z.number(),
  volume: z.number(),
  grossPnl: z.number(),
  costs: z.number(),
  netPnl: z.number(),
  rMultiple: z.number().nullable(),
  exitReason: exitReasonSchema,
  commission: z.number().default(0),
  swap: z.number().default(0),
});
export type Trade = z.infer<typeof tradeSchema>;

export const indicatorSnapshotSchema = z.object({
  ema20: z.number().nullable(),
  ema50: z.number().nullable(),
  ema200: z.number().nullable(),
  rsi14: z.number().nullable(),
  atr14: z.number().nullable(),
});
export type IndicatorSnapshot = z.infer<typeof indicatorSnapshotSchema>;

export const signalConditionSchema = z.object({
  id: z.string(),
  label: z.string(),
  detail: z.string(),
  satisfied: z.boolean(),
});
export type SignalCondition = z.infer<typeof signalConditionSchema>;

export const strategySignalSchema = z.object({
  symbol: z.string(),
  strategy: z.string(),
  action: signalActionSchema,
  direction: directionSchema,
  timestamp: z.string().datetime(),
  indicators: indicatorSnapshotSchema,
  reason: z.string(),
  conditions: z.array(signalConditionSchema),
  summary: z.string(),
});
export type StrategySignal = z.infer<typeof strategySignalSchema>;

export const strategySnapshotSchema = z.object({
  id: z.string(),
  name: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  status: botStatusSchema,
  currentSignal: strategySignalSchema,
  recentSignals: z.array(strategySignalSchema),
});
export type StrategySnapshot = z.infer<typeof strategySnapshotSchema>;

export const connectionStatusSchema = z.enum(["CONNECTED", "DISCONNECTED", "RECONNECTING"]);
export type ConnectionStatus = z.infer<typeof connectionStatusSchema>;

export const riskCategorySchema = z.enum([
  "account",
  "trade",
  "daily",
  "drawdown",
  "exposure",
]);
export type RiskCategory = z.infer<typeof riskCategorySchema>;

export const riskLimitSchema = z.object({
  key: z.string(),
  label: z.string(),
  category: riskCategorySchema,
  configuredLimit: z.number(),
  currentValue: z.number(),
  unit: z.enum(["percent", "count", "lots", "currency"]),
});
export type RiskLimit = z.infer<typeof riskLimitSchema>;

export const riskSnapshotSchema = z.object({
  equity: z.number(),
  riskPerTradePct: z.number(),
  limits: z.array(riskLimitSchema),
  updatedAt: z.string().datetime(),
});
export type RiskSnapshot = z.infer<typeof riskSnapshotSchema>;

export const backtestRunStatusSchema = z.enum([
  "completed",
  "insufficient_data",
  "data_validation_failed",
]);
export type BacktestRunStatus = z.infer<typeof backtestRunStatusSchema>;

export const backtestQualityStatusSchema = z.enum(["VALID", "WARNING", "INSUFFICIENT"]);
export type BacktestQualityStatus = z.infer<typeof backtestQualityStatusSchema>;

export const backtestDatasetSchema = z.object({
  totalCandles: z.number(),
  startTimestamp: z.string().datetime().nullable(),
  endTimestamp: z.string().datetime().nullable(),
  durationDays: z.number(),
  timezone: z.string(),
  duplicateTimestamps: z.number(),
  missingPeriods: z.number(),
  missingBarsTotal: z.number(),
  weekendGaps: z.number(),
  sessionGaps: z.number(),
  isSorted: z.boolean(),
  isValidOhlc: z.boolean(),
  isMeaningful: z.boolean(),
  minRequiredCandles: z.number(),
  recommendedCandles: z.number(),
  qualityStatus: backtestQualityStatusSchema,
});
export type BacktestDataset = z.infer<typeof backtestDatasetSchema>;

export const backtestExecutionConfigSchema = z.object({
  initialBalance: z.number(),
  riskPerTradePct: z.number(),
  maxDailyLossPct: z.number(),
  maxDrawdownPct: z.number(),
  maxOpenPositions: z.number(),
  maxPositionLots: z.number(),
  spreadPoints: z.number(),
  slippagePoints: z.number(),
  commissionPerLot: z.number(),
  swapPerLotPerDay: z.number(),
  warmupBars: z.number(),
});
export type BacktestExecutionConfig = z.infer<typeof backtestExecutionConfigSchema>;

export const backtestAssumptionsSchema = z.object({
  candleTiming: z.string(),
  execution: z.string(),
  spread: z.string(),
  slippage: z.string(),
  commission: z.string(),
  swap: z.string(),
  exitCosts: z.string(),
  positionLimit: z.string(),
  endOfData: z.string(),
  positionSizing: z.string(),
  sameBarExitRule: z.string(),
});
export type BacktestAssumptions = z.infer<typeof backtestAssumptionsSchema>;

export const backtestTradeRecordSchema = z.object({
  tradeId: z.number(),
  direction: z.enum(["LONG", "SHORT"]),
  volume: z.number(),
  entryPrice: z.number(),
  exitPrice: z.number(),
  stopLoss: z.number(),
  takeProfit: z.number(),
  entryTime: z.string().datetime(),
  exitTime: z.string().datetime(),
  exitReason: exitReasonSchema,
  grossPnl: z.number(),
  commission: z.number(),
  swap: z.number(),
  netPnl: z.number(),
  barsHeld: z.number(),
  rMultiple: z.number().nullable(),
  signalReason: z.string(),
});
export type BacktestTradeRecord = z.infer<typeof backtestTradeRecordSchema>;

export const backtestPerformanceSchema = z.object({
  totalTrades: z.number(),
  winningTrades: z.number(),
  losingTrades: z.number(),
  winRate: z.number(),
  grossProfit: z.number(),
  grossLoss: z.number(),
  netProfit: z.number(),
  totalCommission: z.number(),
  totalSwap: z.number(),
  profitFactor: z.number().nullable(),
  expectancy: z.number(),
  averageWin: z.number(),
  averageLoss: z.number(),
  averageTrade: z.number().nullable(),
  averageR: z.number().nullable(),
  largestWin: z.number().nullable(),
  largestLoss: z.number().nullable(),
  maxConsecutiveWins: z.number(),
  maxConsecutiveLosses: z.number(),
  initialBalance: z.number(),
  finalBalance: z.number(),
  returnPct: z.number(),
  maxDrawdownPct: z.number(),
  maxDrawdownUsd: z.number(),
  maxDrawdownDurationBars: z.number().nullable(),
  currentDrawdownPct: z.number().nullable(),
  averageTradeDurationBars: z.number().nullable(),
});
export type BacktestPerformance = z.infer<typeof backtestPerformanceSchema>;

export const backtestRAnalysisSchema = z.object({
  averageR: z.number().nullable(),
  winningRAverage: z.number().nullable(),
  losingRAverage: z.number().nullable(),
  bestR: z.number().nullable(),
  worstR: z.number().nullable(),
  rMultiples: z.array(z.number()),
});
export type BacktestRAnalysis = z.infer<typeof backtestRAnalysisSchema>;

export const monthlyPerformanceSchema = z.object({
  month: z.string(),
  netPnl: z.number(),
  returnPct: z.number().nullable(),
  trades: z.number(),
  winRate: z.number(),
});
export type MonthlyPerformance = z.infer<typeof monthlyPerformanceSchema>;

export const backtestClassificationSchema = z.object({
  classification: z.string(),
  rationale: z.array(z.string()),
});
export type BacktestClassification = z.infer<typeof backtestClassificationSchema>;

/** Comparison-ready summary for run list / future Phase 10.x. */
export const backtestRunSummarySchema = z.object({
  id: z.string(),
  strategy: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  status: backtestRunStatusSchema,
  generatedAt: z.string().datetime(),
  periodStart: z.string().datetime().nullable(),
  periodEnd: z.string().datetime().nullable(),
  netProfit: z.number().nullable(),
  returnPct: z.number().nullable(),
  maxDrawdownPct: z.number().nullable(),
  totalTrades: z.number().nullable(),
});
export type BacktestRunSummary = z.infer<typeof backtestRunSummarySchema>;

export const backtestReportSchema = z.object({
  id: z.string(),
  strategy: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  status: backtestRunStatusSchema,
  generatedAt: z.string().datetime(),
  message: z.string().nullable(),
  periodStart: z.string().datetime().nullable(),
  periodEnd: z.string().datetime().nullable(),
  dataset: backtestDatasetSchema.nullable(),
  execution: backtestExecutionConfigSchema.nullable(),
  performance: backtestPerformanceSchema.nullable(),
  assumptions: backtestAssumptionsSchema.nullable(),
  classification: backtestClassificationSchema.nullable(),
  equityCurve: z.array(equityPointSchema),
  drawdownCurve: z.array(equityPointSchema),
  trades: z.array(backtestTradeRecordSchema),
  monthlyPerformance: z.array(monthlyPerformanceSchema),
  rAnalysis: backtestRAnalysisSchema.nullable(),
});
export type BacktestReport = z.infer<typeof backtestReportSchema>;

export const candleEngineStatusSchema = z.object({
  status: botStatusSchema,
  lastProcessedAt: z.string().nullable(),
  lastClosedAt: z.string().nullable(),
  lastUpdateAt: z.string().nullable(),
  dataSource: z.string(),
});
export type CandleEngineStatus = z.infer<typeof candleEngineStatusSchema>;

export const signalEngineStatusSchema = z.object({
  status: botStatusSchema,
  strategy: z.string(),
  lastProcessedCandle: z.string().nullable(),
  lastSignal: z.string().nullable(),
  lastSignalAt: z.string().nullable(),
  dataSource: z.string(),
});
export type SignalEngineStatus = z.infer<typeof signalEngineStatusSchema>;

export const paperExecutionStatusSchema = z.object({
  status: botStatusSchema,
  mode: z.string(),
  balance: z.number(),
  equity: z.number(),
  openPositions: z.number().int(),
  lastExecution: z.string().nullable(),
  lastExecutionAt: z.string().nullable(),
  sessionId: z.string().nullable().optional(),
  accountKind: z.string().optional(),
});
export type PaperExecutionStatus = z.infer<typeof paperExecutionStatusSchema>;

export const paperPositionSchema = z.object({
  positionId: z.string(),
  symbol: z.string(),
  side: z.enum(["LONG", "SHORT", "FLAT"]),
  volume: z.number(),
  entryPrice: z.number(),
  currentPrice: z.number(),
  stopLoss: z.number().nullable(),
  takeProfit: z.number().nullable(),
  unrealizedPnl: z.number(),
  openedAt: z.string(),
  status: z.string(),
});
export type PaperPosition = z.infer<typeof paperPositionSchema>;

export const paperTradeRowSchema = z.object({
  time: z.string(),
  symbol: z.string(),
  side: z.enum(["LONG", "SHORT", "FLAT"]),
  volume: z.number(),
  entry: z.number().nullable(),
  stopLoss: z.number().nullable(),
  takeProfit: z.number().nullable(),
  exit: z.number().nullable(),
  pnl: z.number().nullable(),
  status: z.string(),
  reason: z.string().nullable(),
});
export type PaperTradeRow = z.infer<typeof paperTradeRowSchema>;

export const paperTradingSchema = z.object({
  status: botStatusSchema,
  mode: z.string(),
  researchOnly: z.boolean(),
  accountKind: z.string().optional(),
  sessionId: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  initialBalance: z.number(),
  balance: z.number(),
  equity: z.number(),
  realizedPnl: z.number(),
  unrealizedPnl: z.number(),
  dailyPnl: z.number(),
  drawdownPct: z.number(),
  openPositions: z.number().int(),
  executionCount: z.number().int().optional(),
  signalCount: z.number().int().optional(),
  candlesProcessed: z.number().int().optional(),
  rejectedCount: z.number().int().optional(),
  lastExecution: z.string().nullable(),
  lastExecutionAt: z.string().nullable(),
  lastSignal: z.string().nullable(),
  positions: z.array(paperPositionSchema).optional().default([]),
  trades: z.array(paperTradeRowSchema),
});
export type PaperTrading = z.infer<typeof paperTradingSchema>;

export const sessionContextSchema = z.object({
  tradingMode: z.string(),
  connectionStatus: connectionStatusSchema,
  accountLabel: z.string(),
  botStatus: botStatusSchema,
  accountProfile: z.enum(["demo", "live"]),
  candleEngine: candleEngineStatusSchema.nullable().optional(),
  signalEngine: signalEngineStatusSchema.nullable().optional(),
  paperExecution: paperExecutionStatusSchema.nullable().optional(),
});
export type SessionContext = z.infer<typeof sessionContextSchema>;

export const accountProfileIdSchema = z.enum(["demo", "live"]);
export type AccountProfileId = z.infer<typeof accountProfileIdSchema>;

export const accountProfileSchema = z.object({
  id: accountProfileIdSchema,
  kind: accountProfileIdSchema,
  label: z.string(),
  configured: z.boolean(),
  login: z.number().nullable(),
  server: z.string().nullable(),
  active: z.boolean(),
});
export type AccountProfile = z.infer<typeof accountProfileSchema>;

export const accountSwitchStateSchema = z.object({
  activeProfile: accountProfileIdSchema,
  tradingMode: z.string(),
  allowLiveTrading: z.boolean(),
  readOnly: z.boolean(),
  liveOrdersEnabled: z.boolean(),
  profiles: z.array(accountProfileSchema),
  note: z.string(),
});
export type AccountSwitchState = z.infer<typeof accountSwitchStateSchema>;

export const systemSettingsSchema = z.object({
  tradingMode: z.string(),
  broker: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  strategy: z.string(),
  riskPerTradePct: z.number(),
  maxDailyLossPct: z.number(),
  maxDrawdownPct: z.number(),
  maxOpenPositions: z.number(),
});
export type SystemSettings = z.infer<typeof systemSettingsSchema>;

export const dashboardOverviewSchema = z.object({
  botStatus: botStatusSchema,
  account: accountSnapshotSchema,
  equityCurve: z.array(equityPointSchema),
  positions: z.array(positionSchema),
  recentTrades: z.array(tradeSchema),
  currentSignal: strategySignalSchema,
});
export type DashboardOverview = z.infer<typeof dashboardOverviewSchema>;

export const quoteFreshnessSchema = z.enum(["LIVE", "STALE", "UNAVAILABLE"]);
export type QuoteFreshness = z.infer<typeof quoteFreshnessSchema>;

export const quoteSchema = z.object({
  symbol: z.string(),
  bid: z.number().nullable(),
  ask: z.number().nullable(),
  last: z.number().nullable(),
  spread: z.number().nullable(),
  digits: z.number().int().nonnegative(),
  available: z.boolean(),
  updatedAt: z.string().datetime(),
  freshness: quoteFreshnessSchema.default("LIVE"),
});
export type Quote = z.infer<typeof quoteSchema>;

export const analysisReasonSchema = z.object({
  code: z.string(),
  passed: z.boolean(),
  message: z.string(),
});
export type AnalysisReason = z.infer<typeof analysisReasonSchema>;

export const tradeAnalysisSchema = z.object({
  symbol: z.string(),
  brokerSymbol: z.string(),
  timeframe: z.string(),
  strategy: z.string().default("ema_rsi_atr_v1"),
  market: z.object({
    bid: z.number().nullable().optional(),
    ask: z.number().nullable().optional(),
    spreadPoints: z.number().nullable().optional(),
    quoteTimestamp: z.string().nullable().optional(),
    quoteAgeSeconds: z.number().nullable().optional(),
  }),
  indicators: z.object({
    ema20: z.number().nullable().optional(),
    ema50: z.number().nullable().optional(),
    ema200: z.number().nullable().optional(),
    rsi14: z.number().nullable().optional(),
    atr14: z.number().nullable().optional(),
    close: z.number().nullable().optional(),
  }),
  regime: z.enum(["BULLISH", "BEARISH", "NEUTRAL"]),
  signal: z.enum(["BUY", "SELL", "WAIT"]),
  executionStatus: z.enum(["READY", "BLOCKED", "NOT_APPLICABLE"]),
  trade: z
    .object({
      entry: z.number(),
      stopLoss: z.number(),
      takeProfit: z.number(),
      riskRewardRatio: z.number(),
    })
    .nullable()
    .optional(),
  sizing: z
    .object({
      equity: z.number(),
      riskPercent: z.number(),
      riskBudgetUsd: z.number(),
      rawVolume: z.number().nullable().optional(),
      normalizedVolume: z.number().nullable().optional(),
      brokerMinVolume: z.number().nullable().optional(),
      brokerMaxVolume: z.number().nullable().optional(),
      brokerVolumeStep: z.number().nullable().optional(),
      estimatedRiskUsd: z.number().nullable().optional(),
      estimatedRiskPct: z.number().nullable().optional(),
      brokerExecutable: z.boolean(),
      riskAcceptable: z.boolean(),
    })
    .nullable()
    .optional(),
  reasons: z.array(analysisReasonSchema),
  blockingReasons: z.array(analysisReasonSchema),
  candleTimestamp: z.string().nullable().optional(),
  generatedAt: z.string(),
  status: accountDataStatusSchema,
  strategySignal: z.enum(["BUY", "SELL", "WAIT"]).nullable().optional(),
  contextAssessment: z
    .enum(["PASS", "CAUTION", "BLOCKED", "NOT_APPLICABLE"])
    .nullable()
    .optional(),
  structure: z
    .object({
      classification: z.enum(["BULLISH", "BEARISH", "RANGE", "UNDETERMINED"]),
      latestSwingHigh: z.number().nullable().optional(),
      latestSwingLow: z.number().nullable().optional(),
      sequence: z.array(z.string()).default([]),
      nearestSupport: z.number().nullable().optional(),
      nearestResistance: z.number().nullable().optional(),
      distanceToSupport: z.number().nullable().optional(),
      distanceToResistance: z.number().nullable().optional(),
      distanceToSupportAtr: z.number().nullable().optional(),
      distanceToResistanceAtr: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
});
export type TradeAnalysis = z.infer<typeof tradeAnalysisSchema>;

export const mtfVolumeSchema = z.object({
  source: z.string(),
  current: z.number().nullable().optional(),
  average: z.number().nullable().optional(),
  ratio: z.number().nullable().optional(),
  state: z.string(),
});

export const mtfPatternSchema = z.object({
  type: z.string(),
  confidence: z.number(),
  evidence: z.array(z.string()).default([]),
});

export const mtfScoreSchema = z.object({
  trendScore: z.number(),
  structureScore: z.number(),
  momentumScore: z.number(),
  locationScore: z.number(),
  volumeScore: z.number(),
  totalScore: z.number(),
});

export const mtfTimeframeSchema = z.object({
  timeframe: z.string(),
  candleTimestamp: z.string().nullable().optional(),
  close: z.number().nullable().optional(),
  trend: z.string(),
  signal: z.enum(["LONG", "SHORT", "NEUTRAL"]),
  confidence: z.number(),
  score: mtfScoreSchema.nullable().optional(),
  ema20: z.number().nullable().optional(),
  ema50: z.number().nullable().optional(),
  ema200: z.number().nullable().optional(),
  rsi14: z.number().nullable().optional(),
  atr14: z.number().nullable().optional(),
  macd: z.number().nullable().optional(),
  macdSignal: z.number().nullable().optional(),
  macdHistogram: z.number().nullable().optional(),
  macdMomentum: z.string(),
  structureClassification: z.string(),
  sequence: z.array(z.string()).default([]),
  nearestSupport: z.number().nullable().optional(),
  nearestResistance: z.number().nullable().optional(),
  volume: mtfVolumeSchema,
  pattern: mtfPatternSchema,
  status: z.string(),
  reasons: z.array(analysisReasonSchema).default([]),
});

export const mtfTakeProfitSchema = z.object({
  level: z.number().int(),
  price: z.number(),
  allocationPct: z.number(),
  rr: z.number(),
  reason: z.string(),
});

export const mtfSetupSchema = z.object({
  type: z.string(),
  state: z.enum([
    "NO_SETUP",
    "WAITING_FOR_ENTRY",
    "ENTRY_ZONE",
    "INVALIDATED",
    "EXPIRED",
  ]),
  entryType: z.string(),
  entryPrice: z.number().nullable().optional(),
  entryZoneLow: z.number().nullable().optional(),
  entryZoneHigh: z.number().nullable().optional(),
  entryReason: z.string(),
  stopLoss: z.number().nullable().optional(),
  slReason: z.string(),
  slDistance: z.number().nullable().optional(),
  slDistanceAtr: z.number().nullable().optional(),
  takeProfits: z.array(mtfTakeProfitSchema).default([]),
  distanceToEntry: z.number().nullable().optional(),
});

export const multiTimeframeAnalysisSchema = z.object({
  symbol: z.string(),
  brokerSymbol: z.string(),
  currentPrice: z.number().nullable().optional(),
  timeframes: z.record(z.string(), mtfTimeframeSchema),
  finalSignal: z.enum(["LONG", "SHORT", "WAIT"]),
  confidenceScore: z.number(),
  confidenceMeaning: z.literal("EVIDENCE_ALIGNMENT"),
  trend: z.string(),
  structureSummary: z.string(),
  keySupports: z.array(z.number()).default([]),
  keyResistances: z.array(z.number()).default([]),
  setup: mtfSetupSchema.nullable().optional(),
  sizing: z
    .object({
      equity: z.number(),
      riskPercent: z.number(),
      riskBudgetUsd: z.number(),
      rawVolume: z.number().nullable().optional(),
      normalizedVolume: z.number().nullable().optional(),
      brokerMinVolume: z.number().nullable().optional(),
      brokerMaxVolume: z.number().nullable().optional(),
      brokerVolumeStep: z.number().nullable().optional(),
      estimatedRiskUsd: z.number().nullable().optional(),
      estimatedRiskPct: z.number().nullable().optional(),
      brokerExecutable: z.boolean(),
      riskAcceptable: z.boolean(),
    })
    .nullable()
    .optional(),
  executionAssessment: z.enum(["READY", "BLOCKED", "NOT_APPLICABLE"]),
  reasons: z.array(analysisReasonSchema).default([]),
  warnings: z.array(analysisReasonSchema).default([]),
  summaryVi: z.array(z.string()).default([]),
  generatedAt: z.string(),
  freshness: z.string(),
});
export type MultiTimeframeAnalysis = z.infer<typeof multiTimeframeAnalysisSchema>;

export const executionCandidateSchema = z.object({
  candidateId: z.string(),
  setupId: z.string(),
  analysisFingerprint: z.string(),
  symbol: z.string(),
  brokerSymbol: z.string(),
  side: z.enum(["LONG", "SHORT"]),
  entry: z.number(),
  stopLoss: z.number(),
  takeProfits: z
    .array(
      z.object({
        level: z.number().int(),
        price: z.number(),
        allocationPct: z.number(),
        rr: z.number(),
        reason: z.string(),
      }),
    )
    .default([]),
  proposedVolume: z.number().nullable().optional(),
  estimatedRiskUsd: z.number().nullable().optional(),
  estimatedRiskPct: z.number().nullable().optional(),
  brokerExecutable: z.boolean(),
  riskAcceptable: z.boolean(),
  createdAt: z.string(),
});

export const executionCandidateStatusSchema = z.object({
  eligible: z.boolean(),
  setupState: z.enum([
    "NO_SETUP",
    "WAITING_FOR_ENTRY",
    "ENTRY_ZONE",
    "INVALIDATED",
    "EXPIRED",
    "SUPERSEDED",
  ]),
  setupId: z.string().nullable().optional(),
  analysisFingerprint: z.string().nullable().optional(),
  candidate: executionCandidateSchema.nullable().optional(),
  reasons: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  strategyId: z.string(),
  confidenceScore: z.number().nullable().optional(),
  confidenceMeaning: z.literal("EVIDENCE_ALIGNMENT"),
  generatedAt: z.string(),
});
export type ExecutionCandidateStatus = z.infer<typeof executionCandidateStatusSchema>;

/** Phase 16.3.4 — MarketSynthesis (backend snake_case → camelCase). */
const unknownString = z.string().catch("UNKNOWN");

const marketDriverSchema = z
  .object({
    driver: z.string(),
    direction_for_gold: z.string().optional(),
    directionForGold: z.string().optional(),
    summary: z.string().optional().default(""),
    evidence_strength: z.string().optional(),
    evidenceStrength: z.string().optional(),
    source_ids: z.array(z.string()).optional(),
    sourceIds: z.array(z.string()).optional(),
  })
  .transform((d) => ({
    driver: d.driver,
    directionForGold: d.directionForGold ?? d.direction_for_gold ?? "UNKNOWN",
    summary: d.summary ?? "",
    evidenceStrength: d.evidenceStrength ?? d.evidence_strength ?? "INSUFFICIENT",
    sourceIds: d.sourceIds ?? d.source_ids ?? [],
  }));

const importantEventSchema = z
  .object({
    event_name: z.string().optional(),
    eventName: z.string().optional(),
    event_type: z.string().optional(),
    eventType: z.string().optional(),
    importance: z.string().optional().default("UNKNOWN"),
    status: z.string().optional().default("UNKNOWN"),
    scheduled_at: z.string().nullable().optional(),
    scheduledAt: z.string().nullable().optional(),
    time_until_event_seconds: z.number().nullable().optional(),
    timeUntilEventSeconds: z.number().nullable().optional(),
    note: z.string().nullable().optional(),
    source_ids: z.array(z.string()).optional(),
    sourceIds: z.array(z.string()).optional(),
  })
  .transform((e) => ({
    eventName: e.eventName ?? e.event_name ?? "UNKNOWN",
    eventType: e.eventType ?? e.event_type ?? "OTHER",
    importance: e.importance ?? "UNKNOWN",
    status: e.status ?? "UNKNOWN",
    scheduledAt: e.scheduledAt ?? e.scheduled_at ?? null,
    timeUntilEventSeconds:
      e.timeUntilEventSeconds ?? e.time_until_event_seconds ?? null,
    note: e.note ?? null,
    sourceIds: e.sourceIds ?? e.source_ids ?? [],
  }));

const sourceRefSchema = z
  .object({
    source_id: z.string().optional(),
    sourceId: z.string().optional(),
    title: z.string().optional().default(""),
    domain: z.string().optional().default(""),
    url: z.string().optional().default(""),
    published_at: z.string().nullable().optional(),
    publishedAt: z.string().nullable().optional(),
    retrieved_at: z.string().nullable().optional(),
    retrievedAt: z.string().nullable().optional(),
    freshness: z.string().nullable().optional(),
    source_type: z.string().nullable().optional(),
    sourceType: z.string().nullable().optional(),
  })
  .transform((s) => ({
    sourceId: s.sourceId ?? s.source_id ?? "",
    title: s.title ?? "",
    domain: s.domain ?? "",
    url: s.url ?? "",
    publishedAt: s.publishedAt ?? s.published_at ?? null,
    retrievedAt: s.retrievedAt ?? s.retrieved_at ?? null,
    freshness: s.freshness ?? null,
    sourceType: s.sourceType ?? s.source_type ?? null,
  }));

export const marketSynthesisSchema = z
  .object({
    schema_version: z.string().optional(),
    schemaVersion: z.string().optional(),
    symbol: z.string(),
    generated_at: z.string().optional(),
    generatedAt: z.string().optional(),
    status: unknownString,
    technical_view: z.record(z.string(), z.unknown()).optional(),
    technicalView: z.record(z.string(), z.unknown()).optional(),
    external_view: z.record(z.string(), z.unknown()).optional(),
    externalView: z.record(z.string(), z.unknown()).optional(),
    synthesis: z
      .object({
        state: z.string().optional(),
        summary: z.string().optional().default(""),
        technical_explanation: z.string().optional(),
        technicalExplanation: z.string().optional(),
        external_explanation: z.string().optional(),
        externalExplanation: z.string().optional(),
        alignment_explanation: z.string().optional(),
        alignmentExplanation: z.string().optional(),
        risk_explanation: z.string().optional(),
        riskExplanation: z.string().optional(),
        uncertainties: z.array(z.string()).optional().default([]),
        what_to_watch: z.array(z.string()).optional(),
        whatToWatch: z.array(z.string()).optional(),
      })
      .optional(),
    synthesis_state: z.string().optional(),
    synthesisState: z.string().optional(),
    sources: z.array(sourceRefSchema).optional().default([]),
    facts: z.array(z.record(z.string(), z.unknown())).optional().default([]),
    ai_metadata: z.record(z.string(), z.unknown()).optional(),
    aiMetadata: z.record(z.string(), z.unknown()).optional(),
    cache: z.record(z.string(), z.unknown()).optional(),
    freshness: z.unknown().optional(),
    note: z.string().optional(),
  })
  .transform((raw) => {
    const technicalView = (raw.technicalView ??
      raw.technical_view ??
      {}) as Record<string, unknown>;
    const externalView = (raw.externalView ??
      raw.external_view ??
      {}) as Record<string, unknown>;
    const synRaw = raw.synthesis;
    const syn = {
      state: synRaw?.state,
      summary: synRaw?.summary ?? "",
      technicalExplanation: synRaw?.technicalExplanation,
      technical_explanation: synRaw?.technical_explanation,
      externalExplanation: synRaw?.externalExplanation,
      external_explanation: synRaw?.external_explanation,
      alignmentExplanation: synRaw?.alignmentExplanation,
      alignment_explanation: synRaw?.alignment_explanation,
      riskExplanation: synRaw?.riskExplanation,
      risk_explanation: synRaw?.risk_explanation,
      uncertainties: synRaw?.uncertainties ?? [],
      whatToWatch: synRaw?.whatToWatch,
      what_to_watch: synRaw?.what_to_watch,
    };
    const aiRaw = (raw.aiMetadata ?? raw.ai_metadata ?? {}) as Record<
      string,
      unknown
    >;

    const topDriversRaw =
      externalView.top_drivers ??
      externalView.topDrivers ??
      externalView.market_drivers ??
      [];
    const eventsRaw =
      externalView.important_events ?? externalView.importantEvents ?? [];

    const drivers = z.array(marketDriverSchema).catch([]).parse(topDriversRaw);
    const events = z.array(importantEventSchema).catch([]).parse(eventsRaw);

    return {
      schemaVersion: raw.schemaVersion ?? raw.schema_version ?? "1.0",
      symbol: raw.symbol,
      generatedAt: raw.generatedAt ?? raw.generated_at ?? "",
      status: String(raw.status || "UNAVAILABLE").toUpperCase(),
      technicalView: {
        primaryTimeframe: String(
          technicalView.primary_timeframe ??
            technicalView.primaryTimeframe ??
            "M15",
        ),
        primaryBias: String(
          technicalView.primary_bias ?? technicalView.primaryBias ?? "UNKNOWN",
        ).toUpperCase(),
        botSignal: String(
          technicalView.bot_signal ?? technicalView.botSignal ?? "WAIT",
        ).toUpperCase(),
        botStrategy: String(
          technicalView.bot_strategy ??
            technicalView.botStrategy ??
            "mtf_technical_v1",
        ),
        setupState: (technicalView.setup_state ??
          technicalView.setupState ??
          null) as string | null,
        executionStatus: (technicalView.execution_status ??
          technicalView.executionStatus ??
          null) as string | null,
        mtfAlignment: String(
          technicalView.mtf_alignment ??
            technicalView.mtfAlignment ??
            "UNKNOWN",
        ).toUpperCase(),
        timeframes: (technicalView.timeframes ?? {}) as Record<
          string,
          { trend?: string; structure?: string }
        >,
        nearestSupport: technicalView.nearest_support ?? technicalView.nearestSupport,
        nearestResistance:
          technicalView.nearest_resistance ?? technicalView.nearestResistance,
        wickRejection: (technicalView.wick_rejection ??
          technicalView.wickRejection ??
          null) as string | null,
        currentPrice: (technicalView.current_price ??
          technicalView.currentPrice ??
          null) as number | null,
      },
      externalView: {
        status: String(
          externalView.status ?? "UNAVAILABLE",
        ).toUpperCase(),
        externalBias: String(
          externalView.external_bias ??
            externalView.externalBias ??
            "INSUFFICIENT_EVIDENCE",
        ).toUpperCase(),
        evidenceStrength: String(
          externalView.evidence_strength ??
            externalView.evidenceStrength ??
            "INSUFFICIENT",
        ).toUpperCase(),
        alignmentWithTechnical: String(
          externalView.alignment_with_technical ??
            externalView.alignmentWithTechnical ??
            "INSUFFICIENT_DATA",
        ).toUpperCase(),
        eventRisk: String(
          externalView.event_risk ?? externalView.eventRisk ?? "UNKNOWN",
        ).toUpperCase(),
        topDrivers: drivers,
        importantEvents: events,
        supportingFactors: (externalView.supporting_factors ??
          externalView.supportingFactors ??
          []) as string[],
        conflictingFactors: (externalView.conflicting_factors ??
          externalView.conflictingFactors ??
          []) as string[],
        sourceCount: Number(
          externalView.source_count ?? externalView.sourceCount ?? 0,
        ),
        freshness: String(
          externalView.freshness ?? "UNDATED",
        ).toUpperCase(),
        providerChips: (() => {
          const rawChips = (externalView.provider_chips ??
            externalView.providerChips ??
            []) as unknown[];
          if (Array.isArray(rawChips) && rawChips.length > 0) {
            return rawChips.map((c) => String(c)).filter(Boolean);
          }
          const domains = (raw.sources ?? []).map((s) =>
            String(s.domain ?? "").toLowerCase(),
          );
          const chips: string[] = [];
          if (domains.some((d) => d.includes("bls.gov"))) chips.push("BLS");
          if (domains.some((d) => d.includes("stlouisfed.org"))) chips.push("FRED");
          if (domains.some((d) => d.includes("federalreserve.gov")))
            chips.push("FED");
          if (
            domains.some(
              (d) =>
                d.includes("treasury.gov") ||
                (d.length > 0 &&
                  !d.includes("bls.gov") &&
                  !d.includes("stlouisfed.org") &&
                  !d.includes("federalreserve.gov")),
            )
          ) {
            // Chỉ gắn RSS khi có domain ngoài BLS/FRED/FED và nằm trong allowlist công khai
            if (domains.some((d) => d.includes("treasury.gov"))) chips.push("RSS");
          }
          return chips;
        })(),
      },
      synthesis: {
        state: String(
          syn.state ??
            raw.synthesisState ??
            raw.synthesis_state ??
            "INSUFFICIENT_CONTEXT",
        ).toUpperCase(),
        summary: syn.summary ?? "",
        technicalExplanation:
          syn.technicalExplanation ?? syn.technical_explanation ?? "",
        externalExplanation:
          syn.externalExplanation ?? syn.external_explanation ?? "",
        alignmentExplanation:
          syn.alignmentExplanation ?? syn.alignment_explanation ?? "",
        riskExplanation: syn.riskExplanation ?? syn.risk_explanation ?? "",
        uncertainties: syn.uncertainties ?? [],
        whatToWatch: syn.whatToWatch ?? syn.what_to_watch ?? [],
      },
      sources: raw.sources ?? [],
      aiMetadata: {
        enabled: Boolean(aiRaw.enabled),
        provider: (aiRaw.provider as string | null) ?? null,
        model: (aiRaw.model as string | null) ?? null,
        used: Boolean(aiRaw.used),
        fallbackUsed: Boolean(aiRaw.fallback_used ?? aiRaw.fallbackUsed),
        latencyMs: (aiRaw.latency_ms ?? aiRaw.latencyMs ?? null) as
          | number
          | null,
        errorType: (aiRaw.error_type ?? aiRaw.errorType ?? null) as
          | string
          | null,
      },
      cache: {
        hit: Boolean((raw.cache as Record<string, unknown> | undefined)?.hit),
        ageSeconds: ((raw.cache as Record<string, unknown> | undefined)
          ?.age_seconds ??
          (raw.cache as Record<string, unknown> | undefined)?.ageSeconds ??
          null) as number | null,
      },
      freshness: raw.freshness ?? null,
      note: raw.note ?? null,
    };
  });

export type MarketSynthesis = z.infer<typeof marketSynthesisSchema>;
export type MarketDriver = MarketSynthesis["externalView"]["topDrivers"][number];
export type MarketContextSource = MarketSynthesis["sources"][number];
export type ImportantMarketEvent =
  MarketSynthesis["externalView"]["importantEvents"][number];

/** Phase 16.3.5 — AI Market Analyst Chat. */
const analystSourceSchema = z
  .object({
    source_id: z.string().optional(),
    sourceId: z.string().optional(),
    title: z.string().optional().default(""),
    domain: z.string().optional().default(""),
    url: z.string().optional().default(""),
    freshness: z.string().nullable().optional(),
  })
  .transform((s) => ({
    sourceId: s.sourceId ?? s.source_id ?? "",
    title: s.title ?? "",
    domain: s.domain ?? "",
    url: s.url ?? "",
    freshness: s.freshness ?? null,
  }));

export const marketAnalystChatResponseSchema = z
  .object({
    schema_version: z.string().optional(),
    schemaVersion: z.string().optional(),
    message_id: z.string().optional(),
    messageId: z.string().optional(),
    session_id: z.string().optional(),
    sessionId: z.string().optional(),
    symbol: z.string(),
    created_at: z.string().optional(),
    createdAt: z.string().optional(),
    answer: z.string(),
    answer_type: z.string().optional(),
    answerType: z.string().optional(),
    intent: z.string().optional().default("GENERAL"),
    context_status: z.string().optional(),
    contextStatus: z.string().optional(),
    context_changed: z.boolean().optional(),
    contextChanged: z.boolean().optional(),
    used_context: z
      .object({
        technical: z.boolean().optional().default(false),
        external: z.boolean().optional().default(false),
        synthesis: z.boolean().optional().default(false),
      })
      .optional(),
    usedContext: z
      .object({
        technical: z.boolean().optional().default(false),
        external: z.boolean().optional().default(false),
        synthesis: z.boolean().optional().default(false),
      })
      .optional(),
    technical_fingerprint: z.string().nullable().optional(),
    technicalFingerprint: z.string().nullable().optional(),
    external_fingerprint: z.string().nullable().optional(),
    externalFingerprint: z.string().nullable().optional(),
    synthesis_fingerprint: z.string().nullable().optional(),
    synthesisFingerprint: z.string().nullable().optional(),
    source_refs: z.array(z.string()).optional(),
    sourceRefs: z.array(z.string()).optional(),
    sources: z.array(analystSourceSchema).optional().default([]),
    warnings: z.array(z.string()).optional().default([]),
    provider_metadata: z.record(z.string(), z.unknown()).optional(),
    providerMetadata: z.record(z.string(), z.unknown()).optional(),
    chat_enabled: z.boolean().optional(),
    chatEnabled: z.boolean().optional(),
    note: z.string().optional().nullable(),
  })
  .transform((raw) => {
    const used = raw.usedContext ?? raw.used_context ?? {
      technical: false,
      external: false,
      synthesis: false,
    };
    const metaRaw = (raw.providerMetadata ??
      raw.provider_metadata ??
      {}) as Record<string, unknown>;
    return {
      schemaVersion: raw.schemaVersion ?? raw.schema_version ?? "1.0",
      messageId: raw.messageId ?? raw.message_id ?? "",
      sessionId: raw.sessionId ?? raw.session_id ?? "",
      symbol: raw.symbol,
      createdAt: raw.createdAt ?? raw.created_at ?? "",
      answer: raw.answer,
      answerType: raw.answerType ?? raw.answer_type ?? "GENERAL_MARKET_QUESTION",
      intent: raw.intent ?? "GENERAL",
      contextStatus: raw.contextStatus ?? raw.context_status ?? "UNKNOWN",
      contextChanged: Boolean(raw.contextChanged ?? raw.context_changed ?? false),
      usedContext: {
        technical: Boolean(used.technical),
        external: Boolean(used.external),
        synthesis: Boolean(used.synthesis),
      },
      technicalFingerprint:
        raw.technicalFingerprint ?? raw.technical_fingerprint ?? null,
      externalFingerprint:
        raw.externalFingerprint ?? raw.external_fingerprint ?? null,
      synthesisFingerprint:
        raw.synthesisFingerprint ?? raw.synthesis_fingerprint ?? null,
      sourceRefs: raw.sourceRefs ?? raw.source_refs ?? [],
      sources: raw.sources ?? [],
      warnings: raw.warnings ?? [],
      providerMetadata: {
        provider: (metaRaw.provider as string | null | undefined) ?? null,
        model: (metaRaw.model as string | null | undefined) ?? null,
        used: Boolean(metaRaw.used ?? false),
        fallbackUsed: Boolean(
          metaRaw.fallbackUsed ?? metaRaw.fallback_used ?? true,
        ),
        latencyMs:
          (metaRaw.latencyMs as number | null | undefined) ??
          (metaRaw.latency_ms as number | null | undefined) ??
          null,
        errorType:
          (metaRaw.errorType as string | null | undefined) ??
          (metaRaw.error_type as string | null | undefined) ??
          null,
      },
      chatEnabled: Boolean(raw.chatEnabled ?? raw.chat_enabled ?? false),
      note: raw.note ?? null,
    };
  });

export type MarketAnalystChatResponse = z.infer<
  typeof marketAnalystChatResponseSchema
>;
