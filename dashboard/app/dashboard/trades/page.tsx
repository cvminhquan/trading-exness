"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { SymbolTabs } from "@/components/market/SymbolTabs";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { OverviewSkeleton } from "@/components/shared/Skeletons";
import { TradeAnalysisSection } from "@/components/trading-analysis/TradeAnalysisSection";
import { Badge } from "@/components/ui/badge";
import { NAV, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { resolveDashboardSymbol } from "@/lib/symbols/config";
import {
  useExecutionCandidateStatus,
  useMultiTimeframeAnalysis,
} from "@/queries/use-trading-queries";

const TradesExplorer = () => {
  const searchParams = useSearchParams();
  const symbol = useMemo(
    () => resolveDashboardSymbol(searchParams.get("symbol")),
    [searchParams],
  );

  const mtfAnalysisQuery = useMultiTimeframeAnalysis(symbol);
  const executionCandidateQuery = useExecutionCandidateStatus(symbol);
  const hrefForSymbol = (s: string) => `/dashboard/trades?symbol=${s}`;

  return (
    <>
      <SymbolTabs activeSymbol={symbol} hrefForSymbol={hrefForSymbol} />

      <QueryState
        isLoading={mtfAnalysisQuery.isLoading}
        isError={mtfAnalysisQuery.isError}
        errorMessage={mtfAnalysisQuery.error?.message}
        onRetry={() => void mtfAnalysisQuery.refetch()}
        loadingFallback={<OverviewSkeleton />}
        section={SECTION_LABELS.trades}
      >
        {mtfAnalysisQuery.data ? (
          <TradeAnalysisSection
            analysis={mtfAnalysisQuery.data}
            eligibility={executionCandidateQuery.data}
          />
        ) : null}
      </QueryState>
    </>
  );
};

export default function TradesPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title={NAV.trades.label}
        description="Signal / Setup Explorer — chỉ đọc. Không đặt lệnh BUY/SELL từ dashboard."
        badge={
          <Badge variant="default" className="normal-case">
            {UI.readOnly}
          </Badge>
        }
      />

      <Suspense fallback={<OverviewSkeleton />}>
        <TradesExplorer />
      </Suspense>
    </div>
  );
}
