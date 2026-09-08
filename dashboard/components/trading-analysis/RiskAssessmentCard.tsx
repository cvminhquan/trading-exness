"use client";

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

  let eligibilityLabel: string = L.na;
  if (analysis.executionAssessment === "READY" || eligibility?.eligible) {
    eligibilityLabel = L.ready;
  } else if (
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && !eligibility.eligible && hasSetup)
  ) {
    eligibilityLabel = L.blocked;
  } else if (!hasSetup) {
    eligibilityLabel = L.na;
  }

  return (
    <section aria-label={L.riskTitle}>
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {L.riskTitle}
      </h3>

      {!sizing ? (
        <p className="mt-2 text-sm text-slate-600">{L.noSetupMessage}</p>
      ) : (
        <dl className="mt-2 space-y-1.5 text-sm">
          <Row label={L.riskBudget} value={formatCurrency(sizing.riskBudgetUsd)} />
          <Row
            label={L.estimatedRisk}
            value={
              sizing.estimatedRiskUsd == null
                ? L.dash
                : formatCurrency(sizing.estimatedRiskUsd)
            }
          />
          <Row
            label={L.proposedVolume}
            value={
              sizing.normalizedVolume == null
                ? L.dash
                : `${formatNumber(sizing.normalizedVolume, 2)} ${L.lot}`
            }
          />
          <Row
            label={L.brokerExecutable}
            value={brokerOk ? L.yes : L.no}
            tone={brokerOk ? "good" : "bad"}
          />
          <Row
            label={L.riskAcceptable}
            value={riskOk ? L.yes : L.no}
            tone={riskOk ? "good" : "bad"}
          />
          <Row
            label={L.executionEligibility}
            value={eligibilityLabel}
            tone={
              eligibilityLabel === L.ready
                ? "good"
                : eligibilityLabel === L.blocked
                  ? "bad"
                  : "neutral"
            }
          />
        </dl>
      )}

      {showRiskConflict ? (
        <p className="mt-2 text-xs text-amber-800">{L.riskOverBudgetMessage}</p>
      ) : null}
    </section>
  );
};

const Row = ({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "bad";
}) => (
  <div className="flex items-baseline justify-between gap-3">
    <dt className="text-xs text-slate-500">{label}</dt>
    <dd
      className={cn(
        "font-medium tabular-nums",
        tone === "good" && "text-emerald-800",
        tone === "bad" && "text-rose-800",
        tone === "neutral" && "text-slate-900",
      )}
    >
      {value}
    </dd>
  </div>
);
