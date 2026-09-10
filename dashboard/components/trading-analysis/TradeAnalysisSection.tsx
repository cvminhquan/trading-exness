"use client";

import { MultiTimeframeDetails } from "@/components/trading-analysis/MultiTimeframeDetails";
import { UnifiedTradingAnalysisCard } from "@/components/trading-analysis/UnifiedTradingAnalysisCard";
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
    <UnifiedTradingAnalysisCard
      analysis={analysis}
      eligibility={eligibility}
    />

    {showTimeframeDetails ? (
      <MultiTimeframeDetails analysis={analysis} />
    ) : null}
  </div>
);
