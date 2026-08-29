"use client";

import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { BacktestPerformance, EquityPoint } from "@/domain";
import { DrawdownChart } from "@/components/shared/DrawdownChart";
import { formatDurationBars, formatPercent } from "@/lib/format";
import { A11Y, METRICS } from "@/lib/i18n/vi";

type BacktestDrawdownSectionProps = {
  drawdownCurve: EquityPoint[];
  performance: BacktestPerformance | null;
};

export const BacktestDrawdownSection = ({
  drawdownCurve,
  performance,
}: BacktestDrawdownSectionProps) => {
  const stats = useMemo(() => {
    if (!performance) return null;
    return [
      { label: METRICS.maxDrawdown, value: formatPercent(performance.maxDrawdownPct) },
      {
        label: "Thời lượng DD tối đa",
        value: formatDurationBars(performance.maxDrawdownDurationBars),
      },
      {
        label: "Drawdown hiện tại",
        value: formatPercent(performance.currentDrawdownPct),
      },
    ];
  }, [performance]);

  return (
    <section aria-label={A11Y.drawdownAnalysis} className="space-y-4">
      {stats ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {stats.map((s) => (
            <Card key={s.label}>
              <CardContent className="py-4">
                <p className="text-xs uppercase text-slate-500">{s.label}</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{s.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
      <DrawdownChart
        data={drawdownCurve}
        title="Drawdown theo thời gian"
        variant="backtest"
      />
    </section>
  );
};
