import { DASHBOARD_SYMBOLS } from "@/lib/symbols/config";

/** Danh sách mặc định “thịnh hành” trên Dashboard (MT5 canonical). */
export const TRENDING_SYMBOLS = DASHBOARD_SYMBOLS;

export const TRENDING_STORAGE_KEY = "exness.dashboard.extraSymbols";

/** Event nội bộ khi watchlist đổi (cùng tab). */
export const WATCHLIST_CHANGED_EVENT = "exness.dashboard.watchlist";

export const MAX_EXTRA_SYMBOLS = 12;

export const normalizeSymbol = (raw: string): string =>
  raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");

export const loadExtraSymbols = (): string[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(TRENDING_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string")
      .map(normalizeSymbol)
      .filter(Boolean)
      .slice(0, MAX_EXTRA_SYMBOLS);
  } catch {
    return [];
  }
};

export const saveExtraSymbols = (symbols: string[]): void => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TRENDING_STORAGE_KEY, JSON.stringify(symbols));
  window.dispatchEvent(new Event(WATCHLIST_CHANGED_EVENT));
};

export const mergeWatchSymbols = (extras: string[]): string[] => {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const symbol of [...TRENDING_SYMBOLS, ...extras]) {
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
  }
  return out;
};
