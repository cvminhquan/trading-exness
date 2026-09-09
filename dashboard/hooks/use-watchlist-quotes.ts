"use client";

import { useSyncExternalStore } from "react";
import type { Quote } from "@/domain";
import {
  WATCHLIST_CHANGED_EVENT,
  loadExtraSymbols,
  mergeWatchSymbols,
} from "@/lib/market/trending";
import { quoteMidPrice, resolveDisplayPrice } from "@/lib/market/quote-price";
import { useQuotes } from "@/queries/use-trading-queries";

const subscribeWatchlist = (onStoreChange: () => void): (() => void) => {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(WATCHLIST_CHANGED_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(WATCHLIST_CHANGED_EVENT, onStoreChange);
  };
};

const getWatchlistSnapshot = (): string => loadExtraSymbols().join(",");

const getServerSnapshot = (): string => "";

/**
 * Một nguồn quote cho toàn dashboard (tabs + hero + trending).
 * Cùng queryKey → cùng giá mid cho mọi symbol đang theo dõi.
 */
export const useWatchlistQuotes = () => {
  const extrasKey = useSyncExternalStore(
    subscribeWatchlist,
    getWatchlistSnapshot,
    getServerSnapshot,
  );
  const extras = extrasKey ? extrasKey.split(",").filter(Boolean) : [];
  const symbols = mergeWatchSymbols(extras);
  const query = useQuotes(symbols);
  const quotes = query.data ?? [];
  const bySymbol = new Map(quotes.map((q) => [q.symbol, q] as const));

  const priceOf = (symbol: string): number | null => {
    const quote = bySymbol.get(symbol);
    return quote ? quoteMidPrice(quote) : null;
  };

  const displayPriceOf = (
    symbol: string,
    analysisPrice?: number | null,
  ): number | null => resolveDisplayPrice(bySymbol.get(symbol), analysisPrice);

  const quoteOf = (symbol: string): Quote | undefined => bySymbol.get(symbol);

  return {
    ...query,
    symbols,
    quotes,
    bySymbol,
    priceOf,
    displayPriceOf,
    quoteOf,
  };
};
