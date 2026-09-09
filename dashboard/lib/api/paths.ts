export const API_V1 = {
  status: "/api/v1/status",
  account: "/api/v1/account",
  accountOverview: "/api/v1/account/overview",
  accountPnlDaily: "/api/v1/account/pnl/daily",
  overview: "/api/v1/overview",
  quotes: "/api/v1/quotes",
  analysis: "/api/v1/analysis",
  analysisSymbol: (symbol: string) =>
    `/api/v1/analysis/${encodeURIComponent(symbol)}`,
  multiTimeframeAnalysis: (symbol: string) =>
    `/api/v1/analysis/${encodeURIComponent(symbol)}/multi-timeframe`,
  executionCandidate: (symbol: string) =>
    `/api/v1/analysis/${encodeURIComponent(symbol)}/execution-candidate`,
  marketSynthesis: (symbol: string) =>
    `/api/v1/analysis/${encodeURIComponent(symbol)}/market-synthesis`,
  positions: "/api/v1/positions",
  trades: "/api/v1/trades",
  strategy: "/api/v1/strategy",
  risk: "/api/v1/risk",
  settings: "/api/v1/settings",
  accounts: "/api/v1/accounts",
  activeAccount: "/api/v1/accounts/active",
  backtests: "/api/v1/backtests",
  backtest: (id: string) => `/api/v1/backtests/${encodeURIComponent(id)}`,
  paper: "/api/v1/paper",
} as const;
