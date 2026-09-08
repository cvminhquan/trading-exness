import type { Quote } from "@/domain";

export const quoteMidPrice = (quote: Quote): number | null => {
  if (!quote.available) return null;
  if (quote.last != null && Number.isFinite(quote.last)) return quote.last;
  if (quote.bid != null && quote.ask != null) return (quote.bid + quote.ask) / 2;
  return quote.bid ?? quote.ask ?? null;
};

/** % thay đổi so với giá mid trước đó trong phiên (không phải 24h CMC). */
export const computeSessionChangePct = (
  current: number | null,
  previous: number | null | undefined,
): number | null => {
  if (current == null || previous == null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
};
