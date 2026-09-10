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
      <h3 className="text-[13px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        {L.riskTitle}
      </h3>

      {!sizing ? (
        <p className="mt-2 text-[14px] text-[var(--foreground-secondary)]">
          {L.noRiskData}
        </p>
      ) : (
        <>
          <div className="mt-3 space-y-2.5">
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
                <p className="mt-0.5 text-right text-[12px] text-[var(--muted)]">
                  {formatNumber(sizing.estimatedRiskPct, 2)}% {L.ofEquity}
                </p>
              ) : null}
            </div>
            <p className="flex justify-between gap-3 text-[12px] text-[var(--muted)]">
              <span>{L.proposedVolume}</span>
              <span className="tabular-nums">
                {sizing.normalizedVolume == null
                  ? L.dash
                  : `${formatNumber(sizing.normalizedVolume, 2)} ${L.lot}`}
              </span>
            </p>
          </div>

          <div className="mt-3 space-y-1 border-t border-[var(--border)] pt-3">
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
            <p className="mt-2 text-[12px] text-[var(--warning)]">
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
    <p className="text-[16px] font-semibold tabular-nums text-[var(--foreground)]">
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
    className="flex min-h-[28px] items-center justify-between gap-2 text-[13px]"
    role="status"
  >
    <span className="flex min-w-0 items-center gap-1.5 text-[var(--foreground-secondary)]">
      {tone === "good" ? (
        <Check className="h-3.5 w-3.5 shrink-0 text-[var(--positive)]" aria-hidden />
      ) : tone === "bad" ? (
        <X className="h-3.5 w-3.5 shrink-0 text-[var(--negative)]" aria-hidden />
      ) : (
        <span
          className="inline-block size-3.5 shrink-0 rounded-full bg-[var(--accent)]/30"
          aria-hidden
        />
      )}
      <span className="truncate">{label}</span>
    </span>
    <span
      className={cn(
        "max-w-[55%] shrink-0 text-right font-semibold uppercase",
        tone === "good" && "text-[var(--positive)]",
        tone === "bad" && "text-[var(--negative)]",
        tone === "info" && "text-[var(--accent)] normal-case",
        tone === "neutral" && "text-[var(--muted)]",
      )}
    >
      {value}
    </span>
  </div>
);
