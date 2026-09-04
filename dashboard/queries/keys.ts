import type { BacktestListParams, TradeListParams } from "@/domain/api/params";

export const tradingKeys = {
  all: ["trading"] as const,
  status: () => [...tradingKeys.all, "status"] as const,
  botStatus: () => [...tradingKeys.status(), "bot-status"] as const,
  account: () => [...tradingKeys.all, "account"] as const,
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
  accounts: () => [...tradingKeys.all, "accounts"] as const,
  paper: () => [...tradingKeys.all, "paper"] as const,
};
