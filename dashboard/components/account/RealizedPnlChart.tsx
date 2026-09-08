"use client";

import type { DailyRealizedPnl } from "@/domain";
import { EmptyState, ErrorState } from "@/components/shared/States";
import { formatCurrency } from "@/lib/format";
import { ACCOUNT_OVERVIEW } from "@/lib/i18n/vi";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type RealizedPnlChartProps = {
  data: DailyRealizedPnl[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
};

export const RealizedPnlChart = ({
  data,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
}: RealizedPnlChartProps) => {
  if (isLoading) {
    return (
      <section
        aria-busy="true"
        aria-label={ACCOUNT_OVERVIEW.realizedHistoryTitle}
        className="surface-card px-5 py-6 text-center text-[14px] text-[var(--muted)]"
      >
        Đang tải biểu đồ...
      </section>
    );
  }

  if (isError) {
    return (
      <ErrorState
        message={errorMessage ?? "Không thể tải lịch sử realized PnL."}
        section={ACCOUNT_OVERVIEW.realizedHistoryTitle}
        onRetry={onRetry}
      />
    );
  }

  const hasValues = data.some((row) => row.realizedPnl !== 0);
  if (!hasValues) {
    return (
      <div className="surface-card px-5 py-4">
        <EmptyState
          title={ACCOUNT_OVERVIEW.realizedHistoryTitle}
          description={ACCOUNT_OVERVIEW.realizedHistoryEmpty}
        />
      </div>
    );
  }

  const chartData = data.map((row) => ({
    date: row.date.slice(5),
    realizedPnl: row.realizedPnl,
  }));
  const total = data.reduce((sum, row) => sum + row.realizedPnl, 0);

  return (
    <section
      className="surface-card h-full px-5 py-4"
      aria-label={ACCOUNT_OVERVIEW.realizedHistoryTitle}
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
            {ACCOUNT_OVERVIEW.realizedHistoryTitle}
          </h3>
          <p
            className="mt-1 text-[22px] font-semibold tabular-nums"
            style={{
              color:
                total > 0
                  ? "var(--positive)"
                  : total < 0
                    ? "var(--negative)"
                    : "var(--foreground)",
            }}
          >
            {formatCurrency(total)}
          </p>
        </div>
      </div>
      <div className="mt-3 h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="2 2"
              vertical={false}
              stroke="var(--border)"
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "var(--muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "var(--muted)" }}
              width={56}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatCurrency(v)}
            />
            <ReferenceLine y={0} stroke="var(--border-strong)" strokeWidth={1} />
            <Tooltip
              cursor={{ fill: "var(--accent-subtle)" }}
              formatter={(value) => formatCurrency(Number(value))}
              labelFormatter={(label) => String(label)}
              contentStyle={{
                borderRadius: 10,
                borderColor: "var(--border)",
                fontSize: 13,
              }}
            />
            <Bar dataKey="realizedPnl" radius={[4, 4, 0, 0]} maxBarSize={28}>
              {chartData.map((entry) => (
                <Cell
                  key={entry.date}
                  fill={
                    entry.realizedPnl >= 0
                      ? "var(--positive)"
                      : "var(--negative)"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
};
