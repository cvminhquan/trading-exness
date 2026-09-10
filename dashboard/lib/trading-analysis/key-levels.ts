/** Presentational helpers for Key Levels — no strategy/S/R invention. */

import type { MultiTimeframeAnalysis } from "@/domain";
import { TF_ORDER } from "@/lib/trading-analysis/mtf-display";

export type KeyLevelSide = "support" | "resistance";

export type KeyLevelView = {
  side: KeyLevelSide;
  /** Inclusive low of deterministic prices in the display cluster. */
  low: number;
  /** Inclusive high of deterministic prices in the display cluster. */
  high: number;
  /** Timeframe whose nearest level best matches this cluster, if any. */
  timeframe: string | null;
  /** Distance from current price to the nearer edge of the cluster. */
  distancePts: number;
  distancePct: number;
};

export type KeyLevelsSnapshot = {
  support: KeyLevelView | null;
  resistance: KeyLevelView | null;
  current: number | null;
  /** True when both sides exist and current is between them. */
  priceBetween: boolean;
};

const _matchTfForLevel = (
  analysis: MultiTimeframeAnalysis,
  side: KeyLevelSide,
  price: number,
): string | null => {
  let bestTf: string | null = null;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const tf of TF_ORDER) {
    const row = analysis.timeframes[tf];
    if (!row) continue;
    const nearest =
      side === "support" ? row.nearestSupport : row.nearestResistance;
    if (nearest == null || !Number.isFinite(nearest)) continue;
    const dist = Math.abs(nearest - price);
    // Prefer equal-or-closer; on tie prefer higher TF (later in TF_ORDER).
    if (dist < bestDist - 1e-9 || (Math.abs(dist - bestDist) <= 1e-9 && dist <= bestDist)) {
      bestDist = dist;
      bestTf = tf;
    }
  }
  // Only claim a TF when the nearest match is essentially the same level.
  if (bestTf == null || bestDist > Math.max(1e-6, Math.abs(price) * 1e-4)) {
    return null;
  }
  return bestTf;
};

const _clusterAround = (
  levels: number[],
  anchor: number,
  atr: number | null,
): { low: number; high: number } => {
  const tol =
    atr != null && atr > 0
      ? atr * 0.5
      : Math.max(Math.abs(anchor) * 0.001, 0.01);
  const near = levels.filter((p) => Math.abs(p - anchor) <= tol);
  const pool = near.length > 0 ? near : [anchor];
  return { low: Math.min(...pool), high: Math.max(...pool) };
};

/**
 * Nearest support below / resistance above current price from existing
 * `keySupports` / `keyResistances` (+ per-TF nearest as fallback).
 * Never invents prices — only selects and lightly clusters known levels.
 */
export const buildKeyLevelsSnapshot = (
  analysis: MultiTimeframeAnalysis,
  currentPrice: number | null | undefined,
): KeyLevelsSnapshot => {
  const current =
    currentPrice != null && Number.isFinite(currentPrice)
      ? currentPrice
      : analysis.currentPrice != null && Number.isFinite(analysis.currentPrice)
        ? analysis.currentPrice
        : null;

  const supports = [
    ...analysis.keySupports,
    ...TF_ORDER.map((tf) => analysis.timeframes[tf]?.nearestSupport).filter(
      (v): v is number => v != null && Number.isFinite(v),
    ),
  ];
  const resistances = [
    ...analysis.keyResistances,
    ...TF_ORDER.map((tf) => analysis.timeframes[tf]?.nearestResistance).filter(
      (v): v is number => v != null && Number.isFinite(v),
    ),
  ];

  const uniqueSorted = (vals: number[]) =>
    [...new Set(vals.map((v) => Math.round(v * 1e6) / 1e6))].sort(
      (a, b) => a - b,
    );

  const supportLevels = uniqueSorted(supports);
  const resistanceLevels = uniqueSorted(resistances);
  const atr = analysis.timeframes.H1?.atr14 ?? analysis.timeframes.M15?.atr14 ?? null;

  let support: KeyLevelView | null = null;
  let resistance: KeyLevelView | null = null;

  if (current != null) {
    const below = supportLevels.filter((p) => p < current);
    const above = resistanceLevels.filter((p) => p > current);
    const supportAnchor =
      below.length > 0 ? below[below.length - 1]! : null;
    const resistanceAnchor = above.length > 0 ? above[0]! : null;

    if (supportAnchor != null) {
      const { low, high } = _clusterAround(supportLevels, supportAnchor, atr);
      const edge = high;
      support = {
        side: "support",
        low,
        high,
        timeframe: _matchTfForLevel(analysis, "support", supportAnchor),
        distancePts: Math.abs(current - edge),
        distancePct: current !== 0 ? (Math.abs(current - edge) / current) * 100 : 0,
      };
    }
    if (resistanceAnchor != null) {
      const { low, high } = _clusterAround(
        resistanceLevels,
        resistanceAnchor,
        atr,
      );
      const edge = low;
      resistance = {
        side: "resistance",
        low,
        high,
        timeframe: _matchTfForLevel(analysis, "resistance", resistanceAnchor),
        distancePts: Math.abs(edge - current),
        distancePct: current !== 0 ? (Math.abs(edge - current) / current) * 100 : 0,
      };
    }
  }

  return {
    support,
    resistance,
    current,
    priceBetween:
      current != null &&
      support != null &&
      resistance != null &&
      current > support.high &&
      current < resistance.low,
  };
};

export const formatLevelRange = (
  level: KeyLevelView,
  formatPrice: (n: number) => string,
): string => {
  if (Math.abs(level.high - level.low) < 1e-9) {
    return formatPrice(level.low);
  }
  return `${formatPrice(level.low)} – ${formatPrice(level.high)}`;
};
