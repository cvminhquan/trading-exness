"use client";

import { Badge } from "@/components/ui/badge";
import { MetricCard, MetricStrip } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { PaperTradeTable } from "@/components/paper/PaperTradeTable";
import { PaperPositionCard } from "@/components/paper/PaperPositionCard";
import { formatCurrency, formatDateTime, formatPercent, formatSignedCurrency } from "@/lib/format";
import { METRICS, NAV, PAPER_STATUS_LABELS, PAPER_TRADING, SECTION_LABELS } from "@/lib/i18n/vi";
import { usePaperTrading } from "@/queries/use-trading-queries";

const executionLabel = (value: string | null): string => {
  if (!value) return PAPER_TRADING.none;
  if (value in PAPER_STATUS_LABELS) {
    return PAPER_STATUS_LABELS[value as keyof typeof PAPER_STATUS_LABELS];
  }
  return value;
};

export default function PaperTradingPage() {
  const { data, isLoading, isError, error, refetch } = usePaperTrading();

  return (
    <div className="space-y-6">
      <PageHeader
        title={PAPER_TRADING.title}
        description={NAV.paper.description}
        badge={
          <Badge variant="warning" className="normal-case">
            {PAPER_TRADING.researchBadge}
          </Badge>
        }
      />

      <p
        role="alert"
        className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
      >
        {PAPER_TRADING.warning}
      </p>
      <p className="text-sm text-slate-600">{PAPER_TRADING.banner}</p>
      <p className="text-xs text-slate-500">{PAPER_TRADING.brokerAccount}</p>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        isEmpty={false}
        emptyTitle={PAPER_TRADING.emptyTitle}
        emptyDescription={PAPER_TRADING.emptyDescription}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={6} />}
        section={SECTION_LABELS.paper}
      >
        {data ? (
          <>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
              {PAPER_TRADING.paperAccount}
            </h2>
            <MetricStrip>
              <MetricCard label={PAPER_TRADING.mode} value={data.mode.toUpperCase()} />
              <MetricCard label={METRICS.balance} value={formatCurrency(data.balance)} />
              <MetricCard label={METRICS.equity} value={formatCurrency(data.equity)} />
              <MetricCard
                label={PAPER_TRADING.openPositions}
                value={String(data.openPositions)}
              />
            </MetricStrip>
            <MetricStrip>
              <MetricCard
                label={METRICS.totalPnl}
                value={formatSignedCurrency(data.realizedPnl)}
                trend={data.realizedPnl >= 0 ? "up" : "down"}
              />
              <MetricCard
                label={METRICS.unrealizedPnl}
                value={formatSignedCurrency(data.unrealizedPnl)}
                trend={data.unrealizedPnl >= 0 ? "up" : "down"}
              />
              <MetricCard
                label={METRICS.todayPnl}
                value={formatSignedCurrency(data.dailyPnl)}
                trend={data.dailyPnl >= 0 ? "up" : "down"}
              />
              <MetricCard label={METRICS.drawdown} value={formatPercent(data.drawdownPct)} />
            </MetricStrip>
            <MetricStrip>
              <MetricCard
                label={PAPER_TRADING.lastExecution}
                value={executionLabel(data.lastExecution)}
                hint={data.lastExecutionAt ? formatDateTime(data.lastExecutionAt) : undefined}
              />
              <MetricCard
                label={PAPER_TRADING.lastSignal}
                value={data.lastSignal ?? PAPER_TRADING.none}
              />
              <MetricCard
                label={PAPER_TRADING.session}
                value={data.sessionId ? data.sessionId.slice(0, 8) : PAPER_TRADING.none}
                hint={data.startedAt ? formatDateTime(data.startedAt) : undefined}
              />
            </MetricStrip>
            {(data.positions ?? []).map((position) => (
              <PaperPositionCard key={position.positionId} position={position} />
            ))}
            {data.trades.length > 0 ? (
              <PaperTradeTable trades={data.trades} />
            ) : (
              <p className="text-sm text-slate-600">{PAPER_TRADING.emptyDescription}</p>
            )}
          </>
        ) : null}
      </QueryState>
    </div>
  );
}
