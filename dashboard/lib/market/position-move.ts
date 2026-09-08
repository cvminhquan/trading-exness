import type { Position } from "@/domain";

/**
 * Unrealized price move % vs entry (not capital ROI / margin ROI).
 *
 * LONG:  (current - entry) / entry * 100
 * SHORT: (entry - current) / entry * 100
 *
 * Only when entry and current are finite and entry ≠ 0.
 * Do not use as account-equity PnL %.
 */
export const computePositionPriceMovePct = (
  position: Pick<Position, "direction" | "entryPrice" | "currentPrice">,
): number | null => {
  const { entryPrice, currentPrice, direction } = position;
  if (
    !Number.isFinite(entryPrice) ||
    !Number.isFinite(currentPrice) ||
    entryPrice === 0
  ) {
    return null;
  }
  if (direction === "LONG") {
    return ((currentPrice - entryPrice) / entryPrice) * 100;
  }
  if (direction === "SHORT") {
    return ((entryPrice - currentPrice) / entryPrice) * 100;
  }
  return null;
};
