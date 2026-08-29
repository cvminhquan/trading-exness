/** Centralized risk utilization thresholds (percent of configured limit). */
export const RISK_THRESHOLDS = {
  normalMax: 70,
  warningMax: 90,
} as const;

export type RiskLevel = "normal" | "warning" | "critical";

export const getRiskLevel = (usagePct: number): RiskLevel => {
  if (usagePct >= RISK_THRESHOLDS.warningMax) return "critical";
  if (usagePct >= RISK_THRESHOLDS.normalMax) return "warning";
  return "normal";
};

/** Centralized risk utilization thresholds (percent of configured limit). */
export { RISK_LEVEL_LABELS } from "@/lib/i18n/vi";
