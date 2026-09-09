import type { Quote } from "@/domain";

export const quoteMidPrice = (quote: Quote): number | null => {
  if (!quote.available) return null;
  if (quote.last != null && Number.isFinite(quote.last)) return quote.last;
  if (quote.bid != null && quote.ask != null) return (quote.bid + quote.ask) / 2;
  return quote.bid ?? quote.ask ?? null;
};

/**
 * Giá hiển thị thống nhất trên UI: luôn ưu tiên mid từ quote API,
 * chỉ fallback sang snapshot phân tích khi chưa có quote.
 */
export const resolveDisplayPrice = (
  quote: Quote | null | undefined,
  analysisPrice: number | null | undefined,
): number | null => {
  const live = quote ? quoteMidPrice(quote) : null;
  if (live != null) return live;
  if (analysisPrice != null && Number.isFinite(analysisPrice)) return analysisPrice;
  return null;
};

/** % thay đổi so với giá mid trước đó trong phiên (không phải 24h CMC). */
export const computeSessionChangePct = (
  current: number | null,
  previous: number | null | undefined,
): number | null => {
  if (current == null || previous == null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
};
