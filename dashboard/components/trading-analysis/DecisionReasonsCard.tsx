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
};

export const DecisionReasonsCard = ({
  analysis,
  eligibility,
}: DecisionReasonsCardProps) => {
  const [showRaw, setShowRaw] = useState(false);
  const items = collectDecisionReasons({
    analysisReasons: analysis.reasons,
    analysisWarnings: analysis.warnings,
    eligibilityReasons: eligibility?.reasons,
    finalSignal: analysis.finalSignal,
    setupState: eligibility?.setupState ?? analysis.setup?.state,
  });
  const hasSetup = hasDirectionalSetup(analysis);
  const setupState = eligibility?.setupState ?? analysis.setup?.state;
  const isBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && !eligibility.eligible && hasSetup);
  const isWaitingEntry = setupState === "WAITING_FOR_ENTRY" && !isBlocked;

  const headline = isBlocked
    ? L.blocked
    : analysis.finalSignal === "WAIT"
      ? "WAIT"
      : isWaitingEntry
        ? L.waitingForEntry
        : L.reasonsTitle;

  const summary = isBlocked
    ? L.blockedSummary
    : analysis.finalSignal === "WAIT"
      ? L.waitMessage
      : isWaitingEntry
        ? L.waitingForEntry
        : L.reasonsTitle;

  return (
    <section
      className={cn(
        "rounded-[var(--radius-card)] border px-5 py-4",
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
          "flex items-center gap-2 text-[15px] font-semibold tracking-wide uppercase",
          isBlocked && "text-[var(--negative)]",
          isWaitingEntry && "text-[var(--warning)]",
          !isBlocked && !isWaitingEntry && "text-[var(--foreground)]",
        )}
      >
        {isBlocked ? <AlertTriangle className="h-4 w-4" aria-hidden /> : null}
        {headline}
      </h3>
      <p className="mt-1 text-[14px] text-[var(--foreground-secondary)]">{summary}</p>

      {items.length === 0 ? (
        <p className="mt-3 text-[14px] text-[var(--muted)]">{L.dash}</p>
      ) : (
        <ul className="mt-3 space-y-1.5 text-[14px] text-[var(--foreground-secondary)]">
          {items.map((item) => (
            <li key={item.code} className="flex gap-2">
              <span className="text-[var(--muted)]" aria-hidden>
                •
              </span>
              <span>{item.label}</span>
            </li>
          ))}
        </ul>
      )}

      {items.length > 0 ? (
        <div className="mt-3">
          <button
            type="button"
            className="text-[13px] font-medium text-[var(--muted)] underline-offset-2 transition-colors hover:text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            onClick={() => setShowRaw((v) => !v)}
            aria-expanded={showRaw}
          >
            {L.technicalDetails}
          </button>
          {showRaw ? (
            <ul className="mt-2 space-y-1 font-mono text-[12px] text-[var(--muted)]">
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
