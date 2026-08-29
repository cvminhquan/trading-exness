import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestPerformance } from "@/domain";
import { PnLValue } from "@/components/shared/PnLValue";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import { METRICS } from "@/lib/i18n/vi";

type PnlBreakdownProps = {
  performance: BacktestPerformance;
};

export const PnlBreakdown = ({ performance }: PnlBreakdownProps) => {
  const otherCosts = performance.totalSwap;
  const grossNet = performance.grossProfit - performance.grossLoss;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phân tích lãi &amp; lỗ</CardTitle>
        <p className="text-sm text-slate-500">
          PnL gộp so với PnL ròng — chi phí giao dịch được hiển thị riêng.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-lg border border-slate-800 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.grossProfit}</p>
            <PnLValue value={performance.grossProfit} className="mt-2 text-xl" />
          </div>
          <div className="rounded-lg border border-slate-800 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.grossLoss}</p>
            <PnLValue value={-performance.grossLoss} className="mt-2 text-xl" />
          </div>
          <div className="rounded-lg border border-slate-800 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.grossPnl}</p>
            <PnLValue value={grossNet} className="mt-2 text-xl" />
          </div>
          <div className="rounded-lg border border-slate-800 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.commission}</p>
            <p className="mt-2 text-xl tabular-nums text-rose-300">
              -{formatCurrency(performance.totalCommission)}
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.swap}</p>
            <p className="mt-2 text-xl tabular-nums text-rose-300">
              {formatSignedCurrency(-Math.abs(otherCosts))}
            </p>
          </div>
          <div className="rounded-lg border border-emerald-900/30 bg-emerald-950/10 p-4">
            <p className="text-xs uppercase text-slate-500">{METRICS.netProfit}</p>
            <PnLValue value={performance.netProfit} className="mt-2 text-2xl font-semibold" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
