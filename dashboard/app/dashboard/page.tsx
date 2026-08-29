"use client";

import { BotStatusIndicator } from "@/components/shared/BotStatusIndicator";
import { EquityChart } from "@/components/shared/EquityChart";
import { MetricCard, MetricStrip } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState, EmptyState } from "@/components/shared/States";
import { OverviewSkeleton } from "@/components/shared/Skeletons";
import { SignalCard } from "@/components/strategy/SignalCard";
import { PositionTable } from "@/components/positions/PositionTable";
import { TradeTable } from "@/components/trades/TradeTable";
import { getRiskLevel } from "@/lib/constants/risk";
import { formatCurrency, formatPercent, formatSignedCurrency } from "@/lib/format";
import { EMPTY, METRICS, NAV, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { useDashboardOverview } from "@/queries/use-trading-queries";

export default function DashboardPage() {
  const { data, isLoading, isError, error, refetch } = useDashboardOverview();

  const unrealizedPnl = data?.positions.reduce((sum, p) => sum + p.unrealizedPnl, 0) ?? 0;
  const drawdownUsage = data ? (data.account.drawdownPct / 5) * 100 : 0;
  const drawdownStatus = getRiskLevel(drawdownUsage);

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.overview.label}
        description={NAV.overview.description}
        badge={data ? <BotStatusIndicator status={data.botStatus} /> : undefined}
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        onRetry={() => void refetch()}
        loadingFallback={<OverviewSkeleton />}
        section={SECTION_LABELS.overview}
      >
        {data ? (
          <>
            <MetricStrip>
              <MetricCard label={METRICS.balance} value={formatCurrency(data.account.balance)} />
              <MetricCard label={METRICS.equity} value={formatCurrency(data.account.equity)} />
              <MetricCard
                label={METRICS.todayPnl}
                value={formatSignedCurrency(data.account.todayPnl)}
                trend={data.account.todayPnl >= 0 ? "up" : "down"}
              />
              <MetricCard
                label={METRICS.totalPnl}
                value={formatSignedCurrency(data.account.totalPnl)}
                trend={data.account.totalPnl >= 0 ? "up" : "down"}
              />
            </MetricStrip>

            <MetricStrip>
              <MetricCard
                label={METRICS.drawdown}
                value={formatPercent(data.account.drawdownPct)}
                hint={UI.drawdownMaxHint}
                status={
                  drawdownStatus === "critical"
                    ? "critical"
                    : drawdownStatus === "warning"
                      ? "warning"
                      : "normal"
                }
              />
              <MetricCard label={METRICS.margin} value={formatCurrency(data.account.margin)} />
              <MetricCard label={METRICS.freeMargin} value={formatCurrency(data.account.freeMargin)} />
              <MetricCard
                label={METRICS.unrealizedPnl}
                value={formatSignedCurrency(unrealizedPnl)}
                trend={unrealizedPnl >= 0 ? "up" : "down"}
              />
            </MetricStrip>

            <EquityChart data={data.equityCurve} />

            {data.positions.length > 0 ? (
              <PositionTable positions={data.positions} compact />
            ) : (
              <EmptyState
                title={EMPTY.noOpenPositions}
                description={EMPTY.noOpenPositionsOverview}
              />
            )}

            <SignalCard signal={data.currentSignal} />

            <section aria-label={METRICS.recentTrades}>
              {data.recentTrades.length > 0 ? (
                <TradeTable trades={data.recentTrades} compact />
              ) : (
                <EmptyState
                  title={EMPTY.noRecentTrades}
                  description={EMPTY.noRecentTradesDescription}
                />
              )}
            </section>
          </>
        ) : null}
      </QueryState>
    </div>
  );
}
