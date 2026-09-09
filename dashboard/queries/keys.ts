import type { BacktestListParams, TradeListParams } from "@/domain/api/params";

export const tradingKeys = {
  all: ["trading"] as const,
  status: () => [...tradingKeys.all, "status"] as const,
  botStatus: () => [...tradingKeys.status(), "bot-status"] as const,
  account: () => [...tradingKeys.all, "account"] as const,
  accountOverview: () => [...tradingKeys.all, "account-overview"] as const,
  accountPnlDaily: (days = 7) => [...tradingKeys.all, "account-pnl-daily", days] as const,
  overview: () => [...tradingKeys.all, "overview"] as const,
  positions: () => [...tradingKeys.all, "positions"] as const,
  trades: (filters?: TradeListParams) =>
    [...tradingKeys.all, "trades", filters ?? {}] as const,
  strategy: () => [...tradingKeys.all, "strategy"] as const,
  risk: () => [...tradingKeys.all, "risk"] as const,
  backtests: (params?: BacktestListParams) =>
    [...tradingKeys.all, "backtests", params ?? {}] as const,
  backtest: (id: string) => [...tradingKeys.backtests(), id] as const,
  settings: () => [...tradingKeys.all, "settings"] as const,
  session: () => [...tradingKeys.all, "session"] as const,
  quotes: () => [...tradingKeys.all, "quotes"] as const,
  quotesFor: (symbols: string[]) =>
    [...tradingKeys.all, "quotes", symbols.join(",")] as const,
  analysis: (symbol = "XAUUSD") => [...tradingKeys.all, "analysis", symbol] as const,
  mtfAnalysis: (symbol = "XAUUSD") =>
    [...tradingKeys.all, "mtf-analysis", symbol] as const,
  executionCandidate: (symbol = "XAUUSD") =>
    [...tradingKeys.all, "execution-candidate", symbol] as const,
  marketSynthesis: (symbol = "XAUUSD") =>
    [...tradingKeys.all, "market-synthesis", symbol] as const,
  accounts: () => [...tradingKeys.all, "accounts"] as const,
  paper: () => [...tradingKeys.all, "paper"] as const,
};
