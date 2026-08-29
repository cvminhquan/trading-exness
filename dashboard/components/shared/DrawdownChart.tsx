"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/domain";
import { formatDateTime, formatPercent } from "@/lib/format";
import { A11Y, METRICS, UI } from "@/lib/i18n/vi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartSkeleton } from "@/components/shared/Skeletons";
import { EmptyState } from "@/components/shared/States";

type DrawdownChartProps = {
  data: EquityPoint[];
  title?: string;
  isLoading?: boolean;
  variant?: "live" | "backtest";
};

export const DrawdownChart = ({
  data,
  title = METRICS.drawdown,
  isLoading = false,
  variant = "live",
}: DrawdownChartProps) => {
  const stats = useMemo(() => {
    if (!data.length) return null;
    const values = data.map((d) => d.equity);
    const current = values[values.length - 1] ?? 0;
    const maximum = Math.max(...values);
    return { current, maximum };
  }, [data]);

  if (isLoading) return <ChartSkeleton height="h-64" />;

  if (!data.length) {
    return (
      <EmptyState
        title={UI.noDrawdownData}
        description={UI.noDrawdownDataDescription}
      />
    );
  }

  return (
    <Card className={variant === "backtest" ? "border-amber-900/30 bg-amber-950/10" : undefined}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {stats ? (
          <p className="text-xs text-slate-500">
            {UI.current} {formatPercent(stats.current)} · {UI.max} {formatPercent(stats.maximum)}
          </p>
        ) : null}
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full" role="img" aria-label={A11Y.drawdownChart}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v: string) => formatDateTime(v).split(",")[0] ?? v}
                stroke="#64748b"
                fontSize={11}
                minTickGap={24}
              />
              <YAxis
                tickFormatter={(v: number) => formatPercent(v)}
                stroke="#64748b"
                fontSize={11}
                width={48}
              />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
                labelFormatter={(label) => formatDateTime(String(label))}
                formatter={(value) => [formatPercent(Number(value)), METRICS.drawdown]}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#fb7185"
                fill="#881337"
                fillOpacity={0.35}
                isAnimationActive={data.length < 500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};
