import type { BacktestReport, BacktestRunSummary } from "@/domain";

export const toBacktestRunSummary = (report: BacktestReport): BacktestRunSummary => ({
  id: report.id,
  strategy: report.strategy,
  symbol: report.symbol,
  timeframe: report.timeframe,
  status: report.status,
  generatedAt: report.generatedAt,
  periodStart: report.periodStart,
  periodEnd: report.periodEnd,
  netProfit: report.performance?.netProfit ?? null,
  returnPct: report.performance?.returnPct ?? null,
  maxDrawdownPct: report.performance?.maxDrawdownPct ?? null,
  totalTrades: report.performance?.totalTrades ?? null,
});
