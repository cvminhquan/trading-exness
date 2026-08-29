import type { BacktestPerformance } from "@/domain";
import { MetricCard, MetricStrip } from "@/components/shared/MetricCard";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/format";
import { A11Y, METRICS } from "@/lib/i18n/vi";

type PerformanceMetricsProps = {
  performance: BacktestPerformance;
};

export const PerformanceMetrics = ({ performance }: PerformanceMetricsProps) => (
  <section aria-label={A11Y.performanceSummary}>
    <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-600">
      Tổng quan hiệu suất
    </h3>
    <MetricStrip className="mb-3">
      <MetricCard
        label={METRICS.netProfit}
        value={formatSignedCurrency(performance.netProfit)}
        trend={performance.netProfit >= 0 ? "up" : "down"}
        className="border-amber-200"
        valueClassName="text-3xl"
      />
      <MetricCard
        label={METRICS.returnPct}
        value={formatPercent(performance.returnPct)}
        hint={`Cuối kỳ ${formatCurrency(performance.finalBalance)}`}
        trend={performance.returnPct >= 0 ? "up" : "down"}
        className="border-amber-200"
        valueClassName="text-3xl"
      />
      <MetricCard
        label={METRICS.profitFactor}
        value={
          performance.profitFactor !== null
            ? formatNumber(performance.profitFactor, 2)
            : "—"
        }
        className="border-amber-200"
        valueClassName="text-3xl"
      />
      <MetricCard
        label={METRICS.maxDrawdown}
        value={formatPercent(performance.maxDrawdownPct)}
        hint={formatCurrency(performance.maxDrawdownUsd)}
        trend="down"
        className="border-amber-200"
        valueClassName="text-3xl"
      />
    </MetricStrip>
    <MetricStrip>
      <MetricCard label={METRICS.winRate} value={formatPercent(performance.winRate)} />
      <MetricCard label={METRICS.expectancy} value={formatCurrency(performance.expectancy)} />
      <MetricCard label={METRICS.totalTrades} value={String(performance.totalTrades)} />
      <MetricCard
        label={METRICS.avgWinLoss}
        value={formatCurrency(performance.averageWin)}
        hint={`Lỗ ${formatCurrency(performance.averageLoss)}`}
      />
    </MetricStrip>
  </section>
);
