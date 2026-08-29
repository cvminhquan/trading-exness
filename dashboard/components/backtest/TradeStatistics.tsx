import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestPerformance } from "@/domain";
import {
  formatCurrency,
  formatDurationBars,
  formatNumber,
  formatPercent,
  formatRMultiple,
} from "@/lib/format";
import { METRICS } from "@/lib/i18n/vi";

type TradeStatisticsProps = {
  performance: BacktestPerformance;
};

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-lg border border-slate-800 p-3">
    <dt className="text-xs uppercase text-slate-500">{label}</dt>
    <dd className="mt-1 text-sm font-medium tabular-nums text-slate-100">{value}</dd>
  </div>
);

export const TradeStatistics = ({ performance }: TradeStatisticsProps) => (
  <Card>
    <CardHeader>
      <CardTitle>Thống kê giao dịch</CardTitle>
    </CardHeader>
    <CardContent className="space-y-6">
      <div>
        <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-500">
          Số lượng
        </h4>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label={METRICS.totalTrades} value={String(performance.totalTrades)} />
          <Stat label="Giao dịch thắng" value={String(performance.winningTrades)} />
          <Stat label="Giao dịch thua" value={String(performance.losingTrades)} />
          <Stat label={METRICS.winRate} value={formatPercent(performance.winRate)} />
        </dl>
      </div>
      <div>
        <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-500">
          Hiệu suất
        </h4>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Lãi trung bình" value={formatCurrency(performance.averageWin)} />
          <Stat label="Lỗ trung bình" value={formatCurrency(performance.averageLoss)} />
          <Stat
            label="Giao dịch trung bình"
            value={
              performance.averageTrade !== null
                ? formatCurrency(performance.averageTrade)
                : "—"
            }
          />
          <Stat
            label="Hệ số R trung bình"
            value={
              performance.averageR !== null
                ? formatRMultiple(performance.averageR)
                : "—"
            }
          />
          <Stat
            label="Lãi lớn nhất"
            value={
              performance.largestWin !== null
                ? formatCurrency(performance.largestWin)
                : "—"
            }
          />
          <Stat
            label="Lỗ lớn nhất"
            value={
              performance.largestLoss !== null
                ? formatCurrency(performance.largestLoss)
                : "—"
            }
          />
          <Stat
            label="Chuỗi thắng liên tiếp"
            value={String(performance.maxConsecutiveWins)}
          />
          <Stat
            label="Chuỗi thua liên tiếp"
            value={String(performance.maxConsecutiveLosses)}
          />
          <Stat
            label="Thời lượng TB"
            value={formatDurationBars(performance.averageTradeDurationBars)}
          />
          <Stat
            label={METRICS.profitFactor}
            value={
              performance.profitFactor !== null
                ? formatNumber(performance.profitFactor, 2)
                : "—"
            }
          />
        </dl>
      </div>
    </CardContent>
  </Card>
);
