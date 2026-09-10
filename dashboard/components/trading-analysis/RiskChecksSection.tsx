"use client";

import { Check, X } from "lucide-react";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { formatCurrency, formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type RiskChecksSectionProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

/** Nested risk block — readiness primary here; volume secondary. */
export const RiskChecksSection = ({
  analysis,
  eligibility,
}: RiskChecksSectionProps) => {
  const sizing = analysis.sizing;
  const hasSetup = hasDirectionalSetup(analysis);
  const brokerOk = sizing?.brokerExecutable === true;
  const riskOk = sizing?.riskAcceptable === true;
  const showRiskConflict = brokerOk && !riskOk;
  const setupState = eligibility?.setupState ?? analysis.setup?.state;

  const eligibleReady =
    analysis.executionAssessment === "READY" || eligibility?.eligible === true;
  const eligibleBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && eligibility.eligible === false && hasSetup);
  const waitingEntry = setupState === "WAITING_FOR_ENTRY" && !eligibleReady;

  let eligibilityLabel: string = L.na;
  let eligibilityTone: "good" | "bad" | "info" | "neutral" = "neutral";
  if (eligibleReady) {
    eligibilityLabel = L.ready;
    eligibilityTone = "good";
  } else if (waitingEntry) {
    eligibilityLabel = L.waitingForEntry;
    eligibilityTone = "info";
  } else if (eligibleBlocked) {
    eligibilityLabel = L.blocked;
    eligibilityTone = "bad";
  }

  return (
    <section aria-label={L.riskTitle}>
      <h3 className="text-[11px] font-bold tracking-[0.08em] text-[var(--muted)] uppercase">
        {L.riskTitle}
      </h3>

      {!sizing ? (
        <p className="mt-2 text-[13px] text-[var(--foreground-secondary)]">
          {L.noRiskData}
        </p>
      ) : (
        <>
          <div className="mt-3.5 space-y-3">
            <Metric
              label={L.riskBudget}
              value={formatCurrency(sizing.riskBudgetUsd)}
            />
            <div>
              <Metric
                label={L.estimatedRisk}
                value={
                  sizing.estimatedRiskUsd == null
                    ? L.dash
                    : formatCurrency(sizing.estimatedRiskUsd)
                }
              />
              {sizing.estimatedRiskPct != null ? (
                <p className="mt-0.5 text-right text-[11px] font-medium text-[var(--muted)]">
                  {formatNumber(sizing.estimatedRiskPct, 2)}% {L.ofEquity}
                </p>
              ) : null}
            </div>
            <p className="flex justify-between gap-3 text-[12px] text-[var(--muted)]">
              <span className="font-medium">{L.proposedVolume}</span>
              <span className="font-medium tabular-nums">
                {sizing.normalizedVolume == null
                  ? L.dash
                  : `${formatNumber(sizing.normalizedVolume, 2)} ${L.lot}`}
              </span>
            </p>
          </div>

          <div className="mt-4 space-y-1.5 border-t border-[var(--border)] pt-3.5">
            <StatusRow
              tone={brokerOk ? "good" : "bad"}
              label={L.brokerExecutable}
              value={brokerOk ? L.yes : L.no}
            />
            <StatusRow
              tone={riskOk ? "good" : "bad"}
              label={L.riskAcceptable}
              value={riskOk ? L.yes : L.no}
            />
            <StatusRow
              tone={eligibilityTone}
              label={L.executionEligibility}
              value={eligibilityLabel}
            />
          </div>

          {showRiskConflict ? (
            <p className="mt-2.5 text-[12px] text-[var(--warning)]">
              {L.riskOverBudgetMessage}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
};

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-baseline justify-between gap-3">
    <p className="text-[12px] font-medium text-[var(--muted)]">{label}</p>
    <p className="text-[17px] font-bold tabular-nums tracking-tight text-[var(--foreground)]">
      {value}
    </p>
  </div>
);

const StatusRow = ({
  tone,
  label,
  value,
}: {
  tone: "good" | "bad" | "info" | "neutral";
  label: string;
  value: string;
}) => (
  <div
    className={cn(
      "flex min-h-[32px] items-center justify-between gap-2 rounded-[var(--radius-control)] px-2.5 py-1.5 text-[13px]",
      tone === "good" && "bg-[var(--positive-subtle)]",
      tone === "bad" && "bg-[var(--negative-subtle)]",
      tone === "info" && "bg-[var(--accent-subtle)]",
      tone === "neutral" && "bg-[var(--surface-subtle)]",
    )}
    role="status"
  >
    <span className="flex min-w-0 items-center gap-1.5 text-[var(--foreground-secondary)]">
      {tone === "good" ? (
        <Check
          className="h-3.5 w-3.5 shrink-0 text-[var(--positive)]"
          strokeWidth={2.5}
          aria-hidden
        />
      ) : tone === "bad" ? (
        <X
          className="h-3.5 w-3.5 shrink-0 text-[var(--negative)]"
          strokeWidth={2.5}
          aria-hidden
        />
      ) : (
        <span
          className="inline-block size-3.5 shrink-0 rounded-full bg-[var(--accent)]/35"
          aria-hidden
        />
      )}
      <span className="truncate text-[12px] font-medium">{label}</span>
    </span>
    <span
      className={cn(
        "max-w-[55%] shrink-0 text-right text-[12px] font-bold tracking-wide uppercase",
        tone === "good" && "text-[var(--positive)]",
        tone === "bad" && "text-[var(--negative)]",
        tone === "info" && "text-[var(--accent)] normal-case tracking-normal",
        tone === "neutral" && "text-[var(--muted)]",
      )}
    >
      {value}
    </span>
  </div>
);
