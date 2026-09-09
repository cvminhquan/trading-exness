"use client";

import { use, useState } from "react";
import { notFound } from "next/navigation";
import { AccountOverviewSection } from "@/components/account/AccountOverviewSection";
import { AccountSafetyPanel } from "@/components/account/AccountSafetyPanel";
import { RealizedPnlChart } from "@/components/account/RealizedPnlChart";
import { SymbolTabs } from "@/components/market/SymbolTabs";
import { PositionTable } from "@/components/positions/PositionTable";
import { QueryState } from "@/components/shared/States";
import { OverviewSkeleton, TableSkeleton } from "@/components/shared/Skeletons";
import { TradeAnalysisSection } from "@/components/trading-analysis/TradeAnalysisSection";
import { MarketContextSection } from "@/components/market-context/MarketContextSection";
import { EMPTY, METRICS, SECTION_LABELS } from "@/lib/i18n/vi";
import {
  DASHBOARD_RESERVED_SEGMENTS,
  isValidMarketSymbol,
  normalizeDashboardSymbol,
} from "@/lib/symbols/config";
import {
  useAccountOverview,
  useExecutionCandidateStatus,
  useMultiTimeframeAnalysis,
  usePositions,
} from "@/queries/use-trading-queries";

type PageProps = {
  params: Promise<{ symbol: string }>;
};

export default function DashboardSymbolPage({ params }: PageProps) {
  const { symbol: raw } = use(params);
  const symbol = normalizeDashboardSymbol(raw);
  const [showAllPositions, setShowAllPositions] = useState(false);

  if (
    (DASHBOARD_RESERVED_SEGMENTS as readonly string[]).includes(raw.toLowerCase()) ||
    !isValidMarketSymbol(symbol)
  ) {
    notFound();
  }

  const accountOverviewQuery = useAccountOverview();
  const positionsQuery = usePositions();
  const mtfAnalysisQuery = useMultiTimeframeAnalysis(symbol);
  const executionCandidateQuery = useExecutionCandidateStatus(symbol);

  const allPositions = positionsQuery.data ?? [];
  const symbolPositions = allPositions.filter((p) => p.symbol === symbol);
  const visiblePositions = showAllPositions ? allPositions : symbolPositions;

  return (
    <div className="space-y-4">
      <QueryState
        isLoading={accountOverviewQuery.isLoading}
        isError={accountOverviewQuery.isError}
        errorMessage={accountOverviewQuery.error?.message}
        onRetry={() => void accountOverviewQuery.refetch()}
        loadingFallback={<OverviewSkeleton />}
        section={SECTION_LABELS.overview}
      >
        {accountOverviewQuery.data ? (
          <AccountOverviewSection overview={accountOverviewQuery.data} />
        ) : null}
      </QueryState>

      {accountOverviewQuery.data ? (
        <AccountSafetyPanel safety={accountOverviewQuery.data.safety} />
      ) : null}

      <SymbolTabs activeSymbol={symbol} />

      <QueryState
        isLoading={mtfAnalysisQuery.isLoading}
        isError={mtfAnalysisQuery.isError}
        errorMessage={mtfAnalysisQuery.error?.message}
        onRetry={() => void mtfAnalysisQuery.refetch()}
        loadingFallback={<OverviewSkeleton />}
        section={SECTION_LABELS.overview}
      >
        {mtfAnalysisQuery.data ? (
          <TradeAnalysisSection
            analysis={mtfAnalysisQuery.data}
            eligibility={executionCandidateQuery.data}
          />
        ) : null}
      </QueryState>

      <div className="grid gap-4 xl:grid-cols-12">
        <section
          className="surface-card px-5 py-4 xl:col-span-8"
          aria-label={`${METRICS.openPositions} ${symbol}`}
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[16px] font-semibold text-[var(--foreground)]">
              {showAllPositions
                ? METRICS.openPositions
                : `${METRICS.openPositions} · ${symbol}`}
            </h2>
            <button
              type="button"
              className="text-[13px] font-semibold text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              onClick={() => setShowAllPositions((v) => !v)}
              aria-pressed={showAllPositions}
            >
              {showAllPositions ? "Chỉ symbol hiện tại" : "Xem tất cả →"}
            </button>
          </div>
          <QueryState
            isLoading={positionsQuery.isLoading}
            isError={positionsQuery.isError}
            errorMessage={positionsQuery.error?.message}
            onRetry={() => void positionsQuery.refetch()}
            loadingFallback={<TableSkeleton rows={3} />}
            section={SECTION_LABELS.positions}
            isEmpty={!positionsQuery.isLoading && visiblePositions.length === 0}
            emptyTitle={EMPTY.noOpenPositions}
            emptyDescription={EMPTY.noOpenPositionsOverview}
          >
            {visiblePositions.length > 0 ? (
              <PositionTable positions={visiblePositions} compact />
            ) : null}
          </QueryState>
        </section>

        <div className="xl:col-span-4">
          <RealizedPnlChart />
        </div>
      </div>

      <MarketContextSection symbol={symbol} />
    </div>
  );
}
