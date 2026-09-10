"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { collectDecisionReasons } from "@/lib/trading-analysis/reason-labels";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type DecisionReasonsCardProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
  /** Nested inside Risk card — no outer card chrome. */
  embedded?: boolean;
  /** Giới hạn số bullet hiển thị (phần còn lại xem Technical details). */
  maxItems?: number;
};

export const DecisionReasonsCard = ({
  analysis,
  eligibility,
  embedded = false,
  maxItems,
}: DecisionReasonsCardProps) => {
  const [showRaw, setShowRaw] = useState(false);
  const items = collectDecisionReasons({
    analysisReasons: analysis.reasons,
    analysisWarnings: analysis.warnings,
    eligibilityReasons: eligibility?.reasons,
    finalSignal: analysis.finalSignal,
    setupState: eligibility?.setupState ?? analysis.setup?.state,
  });
  const visibleItems =
    maxItems != null && maxItems > 0 ? items.slice(0, maxItems) : items;
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  const hasSetup = hasDirectionalSetup(analysis);
  const setupState = eligibility?.setupState ?? analysis.setup?.state;
  const isBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && !eligibility.eligible && hasSetup);
  const isWaitingEntry = setupState === "WAITING_FOR_ENTRY" && !isBlocked;

  const headline = L.reasonsTitle;

  const summary = isBlocked
    ? L.blockedSummary
    : analysis.finalSignal === "WAIT"
      ? L.waitMessage
      : isWaitingEntry
        ? L.waitingForEntry
        : null;

  return (
    <section
      className={cn(
        "rounded-[var(--radius-tab)] border",
        embedded ? "px-3 py-2.5" : "px-5 py-4",
        isBlocked &&
          "border-[var(--negative)]/25 bg-[var(--negative-subtle)]",
        isWaitingEntry &&
          "border-[var(--warning)]/25 bg-[var(--warning-subtle)]",
        !isBlocked &&
          !isWaitingEntry &&
          "border-[var(--border)] bg-[var(--surface-subtle)]",
      )}
      aria-label={headline}
    >
      <h3
        className={cn(
          "flex items-center gap-1.5 font-bold tracking-[0.06em] uppercase",
          embedded ? "text-[11px] text-[var(--muted)]" : "text-[15px] text-[var(--foreground)]",
        )}
      >
        {isBlocked ? (
          <AlertTriangle className="h-3.5 w-3.5 text-[var(--negative)]" aria-hidden />
        ) : null}
        {headline}
      </h3>
      {summary ? (
        <p
          className={cn(
            "text-[var(--foreground-secondary)]",
            embedded ? "mt-1 text-[12px] leading-snug" : "mt-1 text-[13px]",
          )}
        >
          {summary}
        </p>
      ) : null}
      {items.length === 0 ? (
        <p className="mt-2 text-[12px] text-[var(--muted)]">
          {L.noDecisionReasons}
        </p>
      ) : (
        <ul
          className={cn(
            "text-[var(--foreground-secondary)]",
            embedded
              ? "mt-2 space-y-1.5 text-[12px] leading-relaxed"
              : "mt-2 space-y-1 text-[13px]",
          )}
        >
          {visibleItems.map((item) => (
            <li key={item.code} className="flex gap-2">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--muted)]" aria-hidden />
              <span className="min-w-0">{item.label}</span>
            </li>
          ))}
          {hiddenCount > 0 ? (
            <li className="text-[12px] text-[var(--muted)]">
              +{hiddenCount} lý do khác
            </li>
          ) : null}
        </ul>
      )}

      {items.length > 0 ? (
        <div className={embedded ? "mt-1.5" : "mt-2"}>
          <button
            type="button"
            className="text-[12px] font-medium text-[var(--muted)] underline-offset-2 transition-colors hover:text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            onClick={() => setShowRaw((v) => !v)}
            aria-expanded={showRaw}
          >
            {L.technicalDetails}
          </button>
          {showRaw ? (
            <ul className="mt-1.5 space-y-0.5 font-mono text-[11px] text-[var(--muted)]">
              {items.map((item) => (
                <li key={`raw-${item.code}`}>{item.code}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
};
