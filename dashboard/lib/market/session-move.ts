import type { Quote } from "@/domain";
import { computeSessionChangePct, quoteMidPrice } from "@/lib/market/quote-price";

export type QuoteSessionMove = {
  /** Absolute change vs first mid observed in this browser session. */
  abs: number;
  /** Percent change vs first mid observed in this browser session. */
  pct: number;
  current: number;
};

/**
 * Domain formula (session, not 24h CMC):
 * baseline = first mid price seen for symbol in this page session
 * abs = currentMid - baseline
 * pct = (currentMid - baseline) / baseline * 100
 *
 * Returns null until a baseline exists and current differs enough to compute.
 * Never fabricates a move without a baseline.
 */
export const computeQuoteSessionMove = (
  currentMid: number | null,
  baselineMid: number | null | undefined,
): QuoteSessionMove | null => {
  if (currentMid == null || baselineMid == null || baselineMid === 0) return null;
  const pct = computeSessionChangePct(currentMid, baselineMid);
  if (pct == null) return null;
  return {
    abs: currentMid - baselineMid,
    pct,
    current: currentMid,
  };
};

export const quoteMoveFromQuote = (
  quote: Quote,
  baselineMid: number | null | undefined,
): QuoteSessionMove | null =>
  computeQuoteSessionMove(quoteMidPrice(quote), baselineMid);
