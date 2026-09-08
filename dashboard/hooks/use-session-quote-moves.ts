"use client";

import { useEffect, useState } from "react";
import type { Quote } from "@/domain";
import { quoteMidPrice } from "@/lib/market/quote-price";
import {
  getSessionMidSeries,
  recordSessionMid,
} from "@/lib/market/session-sparkline";
import {
  computeQuoteSessionMove,
  type QuoteSessionMove,
} from "@/lib/market/session-move";

/** First mid per symbol for this browser tab session (not 24h CMC). */
const sessionBaselines = new Map<string, number>();

export type SessionQuoteState = {
  move: QuoteSessionMove | null;
  /** Mid samples recorded this session (≥2 mới đủ vẽ sparkline). */
  series: number[];
};

/**
 * Exposes abs/% moves + session mid series for sparklines.
 * Series chỉ chứa điểm mid thật từ quote API — không fabricate.
 */
export const useSessionQuoteMoves = (
  quotes: Quote[],
): Record<string, SessionQuoteState> => {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let changed = false;
    for (const quote of quotes) {
      const mid = quoteMidPrice(quote);
      if (mid == null) continue;
      if (sessionBaselines.get(quote.symbol) == null) {
        sessionBaselines.set(quote.symbol, mid);
      }
      const before = getSessionMidSeries(quote.symbol).length;
      const after = recordSessionMid(quote.symbol, mid).length;
      if (after !== before) changed = true;
    }
    if (changed) setTick((n) => n + 1);
  }, [quotes]);

  const next: Record<string, SessionQuoteState> = {};
  for (const quote of quotes) {
    const mid = quoteMidPrice(quote);
    const series = getSessionMidSeries(quote.symbol);
    const baseline = sessionBaselines.get(quote.symbol);
    next[quote.symbol] = {
      series,
      move:
        mid == null || baseline == null
          ? null
          : computeQuoteSessionMove(mid, baseline),
    };
  }

  // tick buộc re-render khi series dài thêm
  void tick;
  return next;
};
