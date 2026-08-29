import { z } from "zod";

export const botStatusSchema = z.enum(["RUNNING", "STOPPED", "ERROR", "DISCONNECTED"]);
export type BotStatus = z.infer<typeof botStatusSchema>;

export const directionSchema = z.enum(["LONG", "SHORT", "FLAT"]);
export type Direction = z.infer<typeof directionSchema>;

export const signalActionSchema = z.enum(["BUY", "SELL", "HOLD"]);
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
});
export type AccountSnapshot = z.infer<typeof accountSnapshotSchema>;

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
});
export type Position = z.infer<typeof positionSchema>;

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

export const sessionContextSchema = z.object({
  tradingMode: z.string(),
  connectionStatus: connectionStatusSchema,
  accountLabel: z.string(),
  botStatus: botStatusSchema,
  accountProfile: z.enum(["demo", "live"]),
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

export const quoteSchema = z.object({
  symbol: z.string(),
  bid: z.number().nullable(),
  ask: z.number().nullable(),
  last: z.number().nullable(),
  spread: z.number().nullable(),
  digits: z.number().int().nonnegative(),
  available: z.boolean(),
  updatedAt: z.string().datetime(),
});
export type Quote = z.infer<typeof quoteSchema>;
