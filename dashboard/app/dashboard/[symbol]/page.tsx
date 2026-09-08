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
import { EMPTY, METRICS, SECTION_LABELS } from "@/lib/i18n/vi";
import {
  DASHBOARD_RESERVED_SEGMENTS,
  isDashboardSymbol,
  normalizeDashboardSymbol,
} from "@/lib/symbols/config";
import {
  useAccountOverview,
  useDailyRealizedPnl,
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
    !isDashboardSymbol(symbol)
  ) {
    notFound();
  }

  const accountOverviewQuery = useAccountOverview();
  const dailyPnlQuery = useDailyRealizedPnl(7);
  const positionsQuery = usePositions();
  const mtfAnalysisQuery = useMultiTimeframeAnalysis(symbol);
  const executionCandidateQuery = useExecutionCandidateStatus(symbol);

  const allPositions = positionsQuery.data ?? [];
  const symbolPositions = allPositions.filter((p) => p.symbol === symbol);
  const visiblePositions = showAllPositions ? allPositions : symbolPositions;

  return (
    <div className="space-y-4">
      {/* Primary workspace: symbol → decision */}
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

      {/* Secondary: positions */}
      <section aria-label={`${METRICS.openPositions} ${symbol}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {showAllPositions
              ? METRICS.openPositions
              : `${METRICS.openPositions} · ${symbol}`}
          </h2>
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-500">
            <input
              type="checkbox"
              checked={showAllPositions}
              onChange={(e) => setShowAllPositions(e.target.checked)}
              className="rounded-sm border-slate-300"
            />
            Hiện tất cả
          </label>
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

      {/* Tertiary: account / safety / PnL */}
      {accountOverviewQuery.data ? (
        <AccountSafetyPanel safety={accountOverviewQuery.data.safety} />
      ) : null}

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

      <RealizedPnlChart
        data={dailyPnlQuery.data ?? []}
        isLoading={dailyPnlQuery.isLoading}
        isError={dailyPnlQuery.isError}
        errorMessage={dailyPnlQuery.error?.message}
        onRetry={() => void dailyPnlQuery.refetch()}
      />
    </div>
  );
}
