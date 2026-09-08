"use client";

import { useMemo } from "react";
import type { Quote } from "@/domain";
import { quoteMidPrice } from "@/lib/market/quote-price";
import {
  computeQuoteSessionMove,
  type QuoteSessionMove,
} from "@/lib/market/session-move";

/** First mid per symbol for this browser tab session (not 24h CMC). */
const sessionBaselines = new Map<string, number>();

/**
 * Exposes abs/% moves vs first mid observed in this browser session.
 */
export const useSessionQuoteMoves = (
  quotes: Quote[],
): Record<string, QuoteSessionMove | null> =>
  useMemo(() => {
    const next: Record<string, QuoteSessionMove | null> = {};
    for (const quote of quotes) {
      const mid = quoteMidPrice(quote);
      if (mid == null) {
        next[quote.symbol] = null;
        continue;
      }
      const baseline = sessionBaselines.get(quote.symbol);
      if (baseline == null) {
        sessionBaselines.set(quote.symbol, mid);
        next[quote.symbol] = null;
        continue;
      }
      next[quote.symbol] = computeQuoteSessionMove(mid, baseline);
    }
    return next;
  }, [quotes]);
