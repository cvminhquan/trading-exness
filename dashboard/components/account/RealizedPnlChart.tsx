"use client";

import { useState } from "react";
import { EmptyState, ErrorState } from "@/components/shared/States";
import { formatCurrency } from "@/lib/format";
import { ACCOUNT_OVERVIEW } from "@/lib/i18n/vi";
import { useDailyRealizedPnl } from "@/queries/use-trading-queries";
import { cn } from "@/lib/utils";
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

const RANGES = [
  { days: 7 as const, label: ACCOUNT_OVERVIEW.realizedRange7d },
  { days: 30 as const, label: ACCOUNT_OVERVIEW.realizedRange30d },
];

type PnlRangeDays = (typeof RANGES)[number]["days"];

export const RealizedPnlChart = () => {
  const [days, setDays] = useState<PnlRangeDays>(7);
  const query = useDailyRealizedPnl(days);
  const data = query.data ?? [];

  const rangeControl = (
    <div
      role="group"
      aria-label={ACCOUNT_OVERVIEW.realizedRangeAria}
      className="inline-flex rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-subtle)] p-0.5"
    >
      {RANGES.map((range) => {
        const selected = days === range.days;
        return (
          <button
            key={range.days}
            type="button"
            onClick={() => setDays(range.days)}
            aria-pressed={selected}
            className={cn(
              "rounded-[calc(var(--radius-control)-2px)] px-2.5 py-1 text-[12px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              selected
                ? "bg-[var(--surface)] text-[var(--accent)] shadow-[var(--shadow-sm)]"
                : "text-[var(--muted)] hover:text-[var(--foreground)]",
            )}
          >
            {range.label}
          </button>
        );
      })}
    </div>
  );

  if (query.isLoading && data.length === 0) {
    return (
      <section
        aria-busy="true"
        aria-label={ACCOUNT_OVERVIEW.realizedHistoryTitle}
        className="surface-card px-5 py-4"
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
            {ACCOUNT_OVERVIEW.realizedHistoryTitle}
          </h3>
          {rangeControl}
        </div>
        <p className="mt-6 text-center text-[14px] text-[var(--muted)]">
          {ACCOUNT_OVERVIEW.realizedLoading}
        </p>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="surface-card px-5 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
            {ACCOUNT_OVERVIEW.realizedHistoryTitle}
          </h3>
          {rangeControl}
        </div>
        <ErrorState
          message={query.error?.message ?? ACCOUNT_OVERVIEW.realizedError}
          section={ACCOUNT_OVERVIEW.realizedHistoryTitle}
          onRetry={() => void query.refetch()}
        />
      </section>
    );
  }

  const hasValues = data.some((row) => row.realizedPnl !== 0);
  if (!hasValues) {
    return (
      <section className="surface-card px-5 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
            {ACCOUNT_OVERVIEW.realizedHistoryTitle}
          </h3>
          {rangeControl}
        </div>
        <EmptyState
          title={ACCOUNT_OVERVIEW.realizedHistoryTitle}
          description={ACCOUNT_OVERVIEW.realizedHistoryEmpty}
        />
      </section>
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
      <div className="flex flex-wrap items-start justify-between gap-3">
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
        {rangeControl}
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
              interval={days === 30 ? 4 : 0}
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
            <Bar
              dataKey="realizedPnl"
              radius={[4, 4, 0, 0]}
              maxBarSize={days === 30 ? 14 : 28}
            >
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
