/** Configured dashboard symbols — shared tabs (canonical MT5 symbols). */

export const DASHBOARD_SYMBOLS = [
  "XAUUSD",
  "BTCUSD",
  "ETHUSD",
  "EURUSD",
  "XAGUSD",
] as const;

export type DashboardSymbol = (typeof DASHBOARD_SYMBOLS)[number];

export const DEFAULT_DASHBOARD_SYMBOL: DashboardSymbol = "XAUUSD";

/** Static sidebar segments that must not be captured by /dashboard/[symbol]. */
export const DASHBOARD_RESERVED_SEGMENTS = [
  "positions",
  "trades",
  "strategy",
  "risk",
  "backtest",
  "paper",
  "settings",
] as const;

export const normalizeDashboardSymbol = (raw: string): string =>
  raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");

export const isDashboardSymbol = (raw: string): raw is DashboardSymbol =>
  (DASHBOARD_SYMBOLS as readonly string[]).includes(normalizeDashboardSymbol(raw));

export const resolveDashboardSymbol = (raw: string | undefined | null): DashboardSymbol => {
  if (!raw) return DEFAULT_DASHBOARD_SYMBOL;
  const n = normalizeDashboardSymbol(raw);
  if (isDashboardSymbol(n)) return n;
  return DEFAULT_DASHBOARD_SYMBOL;
};

export const dashboardSymbolHref = (symbol: string): string =>
  `/dashboard/${normalizeDashboardSymbol(symbol)}`;
