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
        className="border-t border-slate-200 py-6 text-center text-sm text-slate-500"
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
      <EmptyState
        title={ACCOUNT_OVERVIEW.realizedHistoryTitle}
        description={ACCOUNT_OVERVIEW.realizedHistoryEmpty}
      />
    );
  }

  const chartData = data.map((row) => ({
    date: row.date.slice(5),
    realizedPnl: row.realizedPnl,
  }));

  return (
    <section
      className="border-t border-slate-200 pt-3"
      aria-label={ACCOUNT_OVERVIEW.realizedHistoryTitle}
    >
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {ACCOUNT_OVERVIEW.realizedHistoryTitle}
      </h3>
      <div className="mt-2 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" vertical={false} stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6b7280" }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fontSize: 10, fill: "#6b7280" }}
              width={48}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatCurrency(v)}
            />
            <ReferenceLine y={0} stroke="#d1d5db" strokeWidth={1} />
            <Tooltip
              formatter={(value) => formatCurrency(Number(value))}
              labelFormatter={(label) => String(label)}
            />
            <Bar dataKey="realizedPnl" radius={[1, 1, 0, 0]} maxBarSize={24}>
              {chartData.map((entry) => (
                <Cell
                  key={entry.date}
                  fill={entry.realizedPnl >= 0 ? "#047857" : "#9f1239"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
};
