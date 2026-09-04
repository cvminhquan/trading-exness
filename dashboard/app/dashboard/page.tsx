"use client";

import Link from "next/link";
import { BotStatusIndicator } from "@/components/shared/BotStatusIndicator";
import { EquityChart } from "@/components/shared/EquityChart";
import { MetricCard, MetricStrip } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState, EmptyState } from "@/components/shared/States";
import { OverviewSkeleton } from "@/components/shared/Skeletons";
import { SignalCard } from "@/components/strategy/SignalCard";
import { WatchlistTable } from "@/components/market/WatchlistTable";
import { PositionTable } from "@/components/positions/PositionTable";
import { TradeTable } from "@/components/trades/TradeTable";
import { Badge } from "@/components/ui/badge";
import { getRiskLevel } from "@/lib/constants/risk";
import { formatCurrency, formatPercent, formatSignedCurrency } from "@/lib/format";
import { EMPTY, METRICS, NAV, PAPER_TRADING, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { useDashboardOverview, useQuotes, useSessionContext } from "@/queries/use-trading-queries";

export default function DashboardPage() {
  const { data, isLoading, isError, error, refetch } = useDashboardOverview();
  const quotesQuery = useQuotes();
  const sessionQuery = useSessionContext();
  const paper = sessionQuery.data?.paperExecution;

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

      {paper ? (
        <Link
          href="/dashboard/paper"
          className="flex flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
          aria-label={PAPER_TRADING.title}
        >
          <span className="flex flex-wrap items-center gap-2">
            <Badge variant="warning" className="normal-case">
              {PAPER_TRADING.researchBadge}
            </Badge>
            <span className="font-medium">{PAPER_TRADING.title}</span>
            <span>
              {PAPER_TRADING.mode} · {formatCurrency(paper.balance)} / {formatCurrency(paper.equity)}
            </span>
          </span>
          <span>{PAPER_TRADING.banner}</span>
        </Link>
      ) : null}

      <WatchlistTable
        quotes={quotesQuery.data ?? []}
        isLoading={quotesQuery.isLoading}
        isError={quotesQuery.isError}
        errorMessage={quotesQuery.error?.message}
        onRetry={() => void quotesQuery.refetch()}
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
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
              {PAPER_TRADING.brokerAccountTitle}
            </h2>
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
              <MetricCard
                label={METRICS.floatingPnl}
                value={formatSignedCurrency(data.account.profit)}
                trend={data.account.profit >= 0 ? "up" : "down"}
              />
              <MetricCard label={METRICS.leverage} value={`1:${data.account.leverage || "—"}`} />
            </MetricStrip>

            <EquityChart data={data.equityCurve} />

              {data.positions.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {METRICS.openPositions} · Exness
                </p>
                <PositionTable positions={data.positions} compact />
              </div>
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
