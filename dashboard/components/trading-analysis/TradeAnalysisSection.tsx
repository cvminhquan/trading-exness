"use client";

import { MultiTimeframeDetails } from "@/components/trading-analysis/MultiTimeframeDetails";
import { RiskAssessmentCard } from "@/components/trading-analysis/RiskAssessmentCard";
import { TradeDecisionHero } from "@/components/trading-analysis/TradeDecisionHero";
import { TradeSetupCard } from "@/components/trading-analysis/TradeSetupCard";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";

type TradeAnalysisSectionProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
  /** Chỉ hiện ở tab Giao dịch — ẩn trên Tổng quan. */
  showTimeframeDetails?: boolean;
};

export const TradeAnalysisSection = ({
  analysis,
  eligibility,
  showTimeframeDetails = false,
}: TradeAnalysisSectionProps) => (
  <div className="space-y-4" aria-label="Phân tích giao dịch">
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:items-stretch">
      <div className="min-w-0">
        <TradeDecisionHero analysis={analysis} eligibility={eligibility} />
      </div>
      <div className="min-w-0">
        <TradeSetupCard analysis={analysis} />
      </div>
      <div className="min-w-0">
        <RiskAssessmentCard analysis={analysis} eligibility={eligibility} />
      </div>
    </div>

    {showTimeframeDetails ? (
      <MultiTimeframeDetails analysis={analysis} />
    ) : null}
  </div>
);
