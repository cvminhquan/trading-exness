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

export const TradeAnalysisSection = ({
  analysis,
  eligibility,
}: TradeAnalysisSectionProps) => (
  <div className="space-y-4" aria-label="Phân tích giao dịch">
    <div className="grid gap-4 xl:grid-cols-12">
      <div className="xl:col-span-6">
        <TradeDecisionHero analysis={analysis} eligibility={eligibility} />
      </div>
      <div className="xl:col-span-3">
        <TradeSetupCard analysis={analysis} />
      </div>
      <div className="flex flex-col gap-4 xl:col-span-3">
        <RiskAssessmentCard analysis={analysis} eligibility={eligibility} />
        <DecisionReasonsCard analysis={analysis} eligibility={eligibility} />
      </div>
    </div>

    <MultiTimeframeDetails analysis={analysis} />
  </div>
);
