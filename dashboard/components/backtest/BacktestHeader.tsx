import { Badge } from "@/components/ui/badge";
import type { BacktestReport } from "@/domain";
import { formatDateTime } from "@/lib/format";
import { BACKTEST_STATUS_LABELS, NAV, UI } from "@/lib/i18n/vi";

const STATUS_VARIANT: Record<
  BacktestReport["status"],
  "success" | "warning" | "danger" | "default"
> = {
  completed: "success",
  insufficient_data: "warning",
  data_validation_failed: "danger",
};

type BacktestHeaderProps = {
  report: BacktestReport;
};

export const BacktestHeader = ({ report }: BacktestHeaderProps) => (
  <header className="space-y-4 rounded-xl border border-amber-200 bg-amber-50 p-5">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-amber-700">
          {UI.historicalSimulation}
        </p>
        <h2 className="mt-1 text-2xl font-semibold text-slate-900">{NAV.backtest.label}</h2>
        <p className="mt-1 text-sm text-slate-600">
          Tạo lúc {formatDateTime(report.generatedAt)}
        </p>
      </div>
      <Badge
        variant={STATUS_VARIANT[report.status]}
        aria-label={`Trạng thái lần chạy ${BACKTEST_STATUS_LABELS[report.status]}`}
      >
        {BACKTEST_STATUS_LABELS[report.status]}
      </Badge>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ["Chiến lược", report.strategy],
        ["Symbol", report.symbol],
        ["Khung thời gian", report.timeframe],
        ["ID lần chạy", report.id],
      ].map(([label, value]) => (
        <div key={String(label)}>
          <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
          <dd className="mt-1 font-medium tabular-nums text-slate-900">{value}</dd>
        </div>
      ))}
    </dl>
  </header>
);
