import type { MultiTimeframeAnalysis } from "@/domain";

/** Khớp `DEFAULT_TF_WEIGHTS` trên engine — chỉ để PRESENT totalScore đã có. */
export const MTF_DISPLAY_WEIGHTS: Record<string, number> = {
  M15: 0.2,
  H1: 0.3,
  H4: 0.3,
  D1: 0.2,
};

export const MTF_LONG_THRESHOLD = 20;
export const MTF_SHORT_THRESHOLD = -20;

export const TF_ORDER = ["M15", "H1", "H4", "D1"] as const;

/** Gom weighted score từ totalScore backend (không tính lại indicator). */
export const computeDisplayWeightedScore = (
  analysis: MultiTimeframeAnalysis,
): number | null => {
  let weighted = 0;
  let weightSum = 0;
  for (const tf of TF_ORDER) {
    const row = analysis.timeframes[tf];
    if (!row?.score || row.status === "INSUFFICIENT") continue;
    const w = MTF_DISPLAY_WEIGHTS[tf] ?? 0;
    weighted += w * row.score.totalScore;
    weightSum += w;
  }
  if (weightSum <= 0) return null;
  return Math.round(weighted * 100) / 100;
};

export const distanceToThreshold = (
  score: number,
): { side: "SHORT" | "LONG" | "INSIDE"; points: number } => {
  if (score <= MTF_SHORT_THRESHOLD) {
    return { side: "SHORT", points: 0 };
  }
  if (score >= MTF_LONG_THRESHOLD) {
    return { side: "LONG", points: 0 };
  }
  const toShort = score - MTF_SHORT_THRESHOLD;
  const toLong = MTF_LONG_THRESHOLD - score;
  if (toShort <= toLong) {
    return { side: "SHORT", points: Math.round(toShort * 100) / 100 };
  }
  return { side: "LONG", points: Math.round(toLong * 100) / 100 };
};

export const hasDirectionalSetup = (analysis: MultiTimeframeAnalysis): boolean => {
  const setup = analysis.setup;
  if (!setup || setup.state === "NO_SETUP") return false;
  return analysis.finalSignal === "LONG" || analysis.finalSignal === "SHORT";
};

export const structureBiasLabel = (
  classification: string | undefined,
  labels: { bullish: string; bearish: string; mixed: string },
): string => {
  const value = (classification ?? "").toUpperCase();
  if (value.includes("BULL")) return labels.bullish;
  if (value.includes("BEAR")) return labels.bearish;
  return labels.mixed;
};

export const formatCandleClock = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
};

export const formatRelativeAgo = (
  iso: string | null | undefined,
  nowMs: number = Date.now(),
): string => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const sec = Math.max(0, Math.floor((nowMs - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  return `${hr}h ago`;
};

export const freshnessTone = (
  freshness: string,
): "neutral" | "warn" | "bad" => {
  const v = freshness.toUpperCase();
  if (v === "LIVE") return "neutral";
  if (v === "STALE") return "warn";
  return "bad";
};
