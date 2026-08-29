"use client";

import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { OverviewSkeleton } from "@/components/shared/Skeletons";
import { BacktestAnalyticsView } from "@/components/backtest/BacktestAnalyticsView";
import { BacktestEmptyState } from "@/components/backtest/BacktestEmptyState";
import { useBacktestReports } from "@/queries/use-trading-queries";
import { A11Y, NAV, UI } from "@/lib/i18n/vi";

export default function BacktestPage() {
  const { data, isLoading, isError, error, refetch } = useBacktestReports();

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.backtest.label}
        description={NAV.backtest.description}
        badge={
          <Badge variant="warning" className="normal-case" aria-label={A11Y.historicalSimulation}>
            {UI.backtestBadge}
          </Badge>
        }
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        isEmpty={!isLoading && (!data || data.length === 0)}
        emptyTitle="Chưa có báo cáo Backtest nào"
        emptyDescription="Chạy mô phỏng lịch sử từ trading engine và nhập báo cáo kết quả vào đây."
        onRetry={() => void refetch()}
        loadingFallback={<OverviewSkeleton />}
        section="backtest"
      >
        {data?.length ? (
          <BacktestAnalyticsView reports={data} />
        ) : (
          <BacktestEmptyState />
        )}
      </QueryState>
    </div>
  );
}
