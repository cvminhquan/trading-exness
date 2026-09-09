/** Helpers for Market Context presentation — no recalculation of market truth. */

import {
  MARKET_ALIGNMENT_LABELS,
  MARKET_BIAS_LABELS,
  MARKET_CONTEXT_STATE_LABELS,
  MARKET_CONTEXT_STATUS_LABELS,
  MARKET_DIRECTION_FOR_GOLD_LABELS,
  MARKET_EVENT_RISK_LABELS,
  MARKET_EVIDENCE_LABELS,
} from "@/lib/i18n/vi";

export type SemanticTone = "positive" | "negative" | "warning" | "neutral" | "info";

export const labelOr = (map: Record<string, string>, value: string): string =>
  map[value] ?? value.replaceAll("_", " ");

export const statusLabel = (status: string): string =>
  labelOr(MARKET_CONTEXT_STATUS_LABELS, status);

export const stateLabel = (state: string): string =>
  labelOr(MARKET_CONTEXT_STATE_LABELS, state);

export const biasLabel = (bias: string): string =>
  labelOr(MARKET_BIAS_LABELS, bias);

export const alignmentLabel = (alignment: string): string =>
  labelOr(MARKET_ALIGNMENT_LABELS, alignment);

export const eventRiskLabel = (risk: string): string =>
  labelOr(MARKET_EVENT_RISK_LABELS, risk);

export const directionForGoldLabel = (direction: string): string =>
  labelOr(MARKET_DIRECTION_FOR_GOLD_LABELS, direction);

export const evidenceLabel = (strength: string): string =>
  labelOr(MARKET_EVIDENCE_LABELS, strength);

export const biasTone = (bias: string): SemanticTone => {
  const v = bias.toUpperCase();
  if (v === "BULLISH" || v === "BULLISH_FOR_GOLD") return "positive";
  if (v === "BEARISH" || v === "BEARISH_FOR_GOLD") return "negative";
  if (v === "MIXED") return "neutral";
  if (v === "CONFLICT") return "warning";
  return "neutral";
};

export const alignmentTone = (alignment: string): SemanticTone => {
  const v = alignment.toUpperCase();
  if (v === "SUPPORT") return "positive";
  if (v === "CONFLICT") return "warning";
  if (v === "MIXED") return "neutral";
  return "neutral";
};

export const eventRiskTone = (risk: string): SemanticTone => {
  const v = risk.toUpperCase();
  if (v === "HIGH") return "warning";
  if (v === "MEDIUM") return "info";
  return "neutral";
};

export const statusBadgeVariant = (
  status: string,
): "default" | "success" | "warning" | "danger" | "info" => {
  switch (status.toUpperCase()) {
    case "AVAILABLE":
      return "success";
    case "PARTIAL":
    case "STALE":
    case "TECHNICAL_ONLY":
      return "warning";
    case "UNAVAILABLE":
      return "danger";
    default:
      return "default";
  }
};

export const toneClasses = (tone: SemanticTone): string => {
  switch (tone) {
    case "positive":
      return "border-[var(--positive)]/20 bg-[var(--positive-subtle)] text-[var(--positive)]";
    case "negative":
      return "border-[var(--negative)]/20 bg-[var(--negative-subtle)] text-[var(--negative)]";
    case "warning":
      return "border-[var(--warning)]/25 bg-[var(--warning-subtle)] text-[var(--warning)]";
    case "info":
      return "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]";
    default:
      return "border-[var(--border)] bg-[var(--surface-subtle)] text-[var(--foreground-secondary)]";
  }
};

/** Only allow safe http(s) URLs for source links. */
export const safeExternalHref = (url: string | null | undefined): string | null => {
  const raw = (url ?? "").trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
};

export const timeframeRoleLabel = (
  tf: string,
): { role: string; label: string } => {
  switch (tf) {
    case "M15":
      return { role: "PRIMARY", label: "M15 — PRIMARY" };
    case "H1":
      return { role: "CONFIRMATION", label: "H1 — CONFIRMATION" };
    case "H4":
      return { role: "CONTEXT", label: "H4 — CONTEXT" };
    case "D1":
      return { role: "MACRO", label: "D1 — MACRO" };
    default:
      return { role: "OTHER", label: tf };
  }
};
