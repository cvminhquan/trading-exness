"use client";

import { DecisionReasonsCard } from "@/components/trading-analysis/DecisionReasonsCard";
import { MultiTimeframeDetails } from "@/components/trading-analysis/MultiTimeframeDetails";
import { RiskAssessmentCard } from "@/components/trading-analysis/RiskAssessmentCard";
import { TradeDecisionHero } from "@/components/trading-analysis/TradeDecisionHero";
import { TradeSetupCard } from "@/components/trading-analysis/TradeSetupCard";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";

type TradeAnalysisSectionProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

/**
 * READ-ONLY trade analysis — primary decision, then setup/risk, then tertiary.
 */
export const TradeAnalysisSection = ({
  analysis,
  eligibility,
}: TradeAnalysisSectionProps) => (
  <div className="space-y-0" aria-label="Phân tích giao dịch">
    <TradeDecisionHero analysis={analysis} eligibility={eligibility} />

    <div className="grid gap-6 border-b border-slate-200 py-4 xl:grid-cols-2 xl:gap-8">
      <TradeSetupCard analysis={analysis} />
      <RiskAssessmentCard analysis={analysis} eligibility={eligibility} />
    </div>

    <DecisionReasonsCard analysis={analysis} eligibility={eligibility} />
    <MultiTimeframeDetails analysis={analysis} />
  </div>
);
