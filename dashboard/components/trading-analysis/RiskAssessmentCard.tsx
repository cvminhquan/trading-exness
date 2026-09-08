"use client";

import { Check, X } from "lucide-react";
import { DecisionReasonsCard } from "@/components/trading-analysis/DecisionReasonsCard";
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
    <section
      className="surface-card flex h-full min-h-0 flex-col px-4 py-3.5"
      aria-label={L.riskTitle}
    >
      <h3 className="text-[15px] font-semibold text-[var(--foreground)]">
        {L.riskTitle}
      </h3>

      {!sizing ? (
        <p className="mt-2 text-[13px] text-[var(--foreground-secondary)]">
          {L.noSetupMessage}
        </p>
      ) : (
        <>
          <div className="mt-3 space-y-2.5">
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

          <div className="mt-3 space-y-1 border-t border-[var(--border)] pt-3">
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
        <p className="mt-2 text-[12px] text-[var(--warning)]">
          {L.riskOverBudgetMessage}
        </p>
      ) : null}

      <div className="mt-3">
        <DecisionReasonsCard
          analysis={analysis}
          eligibility={eligibility}
          embedded
          maxItems={3}
        />
      </div>
    </section>
  );
};

const Metric = ({ value, label }: { value: string; label: string }) => (
  <div className="flex items-baseline justify-between gap-3">
    <p className="text-[12px] font-medium text-[var(--muted)]">{label}</p>
    <p className="text-[17px] font-semibold tabular-nums text-[var(--foreground)]">
      {value}
    </p>
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
      className="flex min-h-[28px] items-center justify-between gap-2 text-[13px]"
      role="status"
    >
      <span className="flex min-w-0 items-center gap-1.5 text-[var(--foreground-secondary)]">
        {bad ? (
          <X className="h-3.5 w-3.5 shrink-0 text-[var(--negative)]" aria-hidden />
        ) : (
          <Check
            className="h-3.5 w-3.5 shrink-0 text-[var(--positive)]"
            aria-hidden
          />
        )}
        <span className="truncate">{label}</span>
      </span>
      <span
        className={cn(
          "shrink-0 font-semibold tabular-nums uppercase",
          bad ? "text-[var(--negative)]" : "text-[var(--positive)]",
        )}
      >
        {value}
      </span>
    </div>
  );
};
