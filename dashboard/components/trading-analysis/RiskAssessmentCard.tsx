"use client";

import { Check, X } from "lucide-react";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { formatCurrency, formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type RiskAssessmentCardProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

export const RiskAssessmentCard = ({
  analysis,
  eligibility,
}: RiskAssessmentCardProps) => {
  const sizing = analysis.sizing;
  const hasSetup = hasDirectionalSetup(analysis);
  const brokerOk = sizing?.brokerExecutable === true;
  const riskOk = sizing?.riskAcceptable === true;
  const showRiskConflict = brokerOk && !riskOk;

  const eligibleReady =
    analysis.executionAssessment === "READY" || eligibility?.eligible === true;
  const eligibleBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && eligibility.eligible === false && hasSetup);

  let eligibilityLabel: string = L.na;
  let eligibilityTone: "good" | "bad" | "neutral" = "neutral";
  if (eligibleReady) {
    eligibilityLabel = L.ready;
    eligibilityTone = "good";
  } else if (eligibleBlocked) {
    eligibilityLabel = L.blocked;
    eligibilityTone = "bad";
  }

  return (
    <section className="surface-card h-full px-5 py-4" aria-label={L.riskTitle}>
      <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
        {L.riskTitle}
      </h3>

      {!sizing ? (
        <p className="mt-3 text-[14px] text-[var(--foreground-secondary)]">
          {L.noSetupMessage}
        </p>
      ) : (
        <>
          <div className="mt-4 space-y-4">
            <Metric
              value={formatCurrency(sizing.riskBudgetUsd)}
              label={L.riskBudget}
            />
            <Metric
              value={
                sizing.estimatedRiskUsd == null
                  ? L.dash
                  : formatCurrency(sizing.estimatedRiskUsd)
              }
              label={L.estimatedRisk}
            />
            <Metric
              value={
                sizing.normalizedVolume == null
                  ? L.dash
                  : `${formatNumber(sizing.normalizedVolume, 2)} ${L.lot}`
              }
              label={L.proposedVolume}
            />
          </div>

          <div className="mt-5 space-y-2.5 border-t border-[var(--border)] pt-4">
            <StatusRow
              ok={brokerOk}
              label={L.brokerExecutable}
              value={brokerOk ? L.yes : L.no}
            />
            <StatusRow
              ok={riskOk}
              label={L.riskAcceptable}
              value={riskOk ? L.yes : L.no}
            />
            <StatusRow
              ok={eligibilityTone === "good"}
              label={L.executionEligibility}
              value={eligibilityLabel}
              forcedBad={eligibilityTone === "bad"}
            />
          </div>
        </>
      )}

      {showRiskConflict ? (
        <p className="mt-3 text-[13px] text-[var(--warning)]">
          {L.riskOverBudgetMessage}
        </p>
      ) : null}
    </section>
  );
};

const Metric = ({ value, label }: { value: string; label: string }) => (
  <div>
    <p className="text-[20px] font-semibold tabular-nums text-[var(--foreground)]">
      {value}
    </p>
    <p className="mt-0.5 text-[12px] font-medium text-[var(--muted)]">{label}</p>
  </div>
);

const StatusRow = ({
  ok,
  label,
  value,
  forcedBad,
}: {
  ok: boolean;
  label: string;
  value: string;
  forcedBad?: boolean;
}) => {
  const bad = forcedBad || !ok;
  return (
    <div
      className="flex min-h-[36px] items-center justify-between gap-3 text-[14px]"
      role="status"
    >
      <span className="flex items-center gap-2 text-[var(--foreground-secondary)]">
        {bad ? (
          <X className="h-4 w-4 text-[var(--negative)]" aria-hidden />
        ) : (
          <Check className="h-4 w-4 text-[var(--positive)]" aria-hidden />
        )}
        {label}
      </span>
      <span
        className={cn(
          "font-semibold tabular-nums uppercase",
          bad ? "text-[var(--negative)]" : "text-[var(--positive)]",
        )}
      >
        {value}
      </span>
    </div>
  );
};
