"use client";

import type { BacktestRunSummary } from "@/domain";
import {
  formatDateTime,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/format";
import { A11Y, BACKTEST_STATUS_LABELS } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type BacktestRunSelectorProps = {
  runs: BacktestRunSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export const BacktestRunSelector = ({
  runs,
  selectedId,
  onSelect,
}: BacktestRunSelectorProps) => (
  <section aria-label={A11Y.backtestRuns}>
    <h3 className="mb-3 text-sm font-medium text-slate-700">Các lần Backtest</h3>
    <div className="flex flex-col gap-2">
      {runs.map((run) => {
        const isSelected = run.id === selectedId;
        return (
          <button
            key={run.id}
            type="button"
            onClick={() => onSelect(run.id)}
            aria-pressed={isSelected}
            className={cn(
              "rounded-lg border px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500",
              isSelected
                ? "border-amber-300 bg-amber-50"
                : "border-slate-200 bg-slate-50 hover:border-slate-300",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-slate-900">
                {run.strategy} · {run.symbol} {run.timeframe}
              </span>
              <span className="text-xs uppercase text-slate-500">
                {BACKTEST_STATUS_LABELS[run.status]}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {run.periodStart && run.periodEnd
                ? `${run.periodStart.slice(0, 10)} → ${run.periodEnd.slice(0, 10)}`
                : "Không có khoảng thời gian"}{" "}
              · {formatDateTime(run.generatedAt)}
            </p>
            {run.netProfit !== null ? (
              <p className="mt-1 text-sm tabular-nums text-slate-600">
                {formatSignedCurrency(run.netProfit)}
                {run.returnPct !== null ? ` · ${formatPercent(run.returnPct)}` : ""}
                {run.maxDrawdownPct !== null
                  ? ` · DD ${formatPercent(run.maxDrawdownPct)}`
                  : ""}
              </p>
            ) : (
              <p className="mt-1 text-sm text-slate-500">Chưa hiển thị chỉ số</p>
            )}
          </button>
        );
      })}
    </div>
  </section>
);
