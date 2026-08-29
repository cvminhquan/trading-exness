"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/domain";
import { formatCurrency, formatDateTime } from "@/lib/format";
import { A11Y, UI } from "@/lib/i18n/vi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartSkeleton } from "@/components/shared/Skeletons";
import { EmptyState } from "@/components/shared/States";

type EquityChartProps = {
  data: EquityPoint[];
  title?: string;
  isLoading?: boolean;
  variant?: "live" | "backtest";
  initialBalance?: number;
};

export const EquityChart = ({
  data,
  title = UI.equityCurve,
  isLoading = false,
  variant = "live",
  initialBalance,
}: EquityChartProps) => {
  const summary = useMemo(() => {
    if (!data.length) return null;
    const start = initialBalance ?? data[0]?.equity ?? 0;
    return {
      start,
      end: data[data.length - 1]?.equity ?? 0,
      pnl: (data[data.length - 1]?.equity ?? 0) - start,
    };
  }, [data, initialBalance]);

  if (isLoading) return <ChartSkeleton />;

  if (!data.length) {
    return (
      <EmptyState
        title={UI.noEquityData}
        description={UI.noEquityDataDescription}
      />
    );
  }

  return (
    <Card className={variant === "backtest" ? "border-amber-900/30 bg-amber-950/10" : undefined}>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{title}</CardTitle>
          {summary ? (
            <p className="mt-1 text-xs text-slate-500">
              {formatCurrency(summary.start)} → {formatCurrency(summary.end)}
              {initialBalance !== undefined ? ` · PnL ${formatCurrency(summary.pnl)}` : ""}
            </p>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-72 w-full" role="img" aria-label={A11Y.equityChart}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v: string) => formatDateTime(v).split(",")[0] ?? v}
                stroke="#64748b"
                fontSize={11}
                minTickGap={24}
              />
              <YAxis
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
                stroke="#64748b"
                fontSize={11}
                width={56}
              />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
                labelFormatter={(label) => formatDateTime(String(label))}
                formatter={(value) => {
                  const equity = Number(value);
                  const pnl =
                    initialBalance !== undefined ? equity - initialBalance : null;
                  return pnl !== null
                    ? [formatCurrency(equity), `${UI.equityLabel} (PnL ${formatCurrency(pnl)})`]
                    : [formatCurrency(equity), UI.equityLabel];
                }}
              />
              {initialBalance !== undefined ? (
                <ReferenceLine
                  y={initialBalance}
                  stroke="#64748b"
                  strokeDasharray="4 4"
                  label={{ value: UI.initial, fill: "#64748b", fontSize: 10 }}
                />
              ) : null}
              <Line
                type="monotone"
                dataKey="equity"
                stroke={variant === "backtest" ? "#fbbf24" : "#38bdf8"}
                strokeWidth={2}
                dot={false}
                isAnimationActive={data.length < 500}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};
