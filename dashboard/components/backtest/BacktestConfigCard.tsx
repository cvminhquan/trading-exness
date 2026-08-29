import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestExecutionConfig } from "@/domain";
import { formatCurrency, formatPercent, formatVolume } from "@/lib/format";
import { METRICS } from "@/lib/i18n/vi";

type BacktestConfigCardProps = {
  execution: BacktestExecutionConfig;
  strategy: string;
};

export const BacktestConfigCard = ({ execution, strategy }: BacktestConfigCardProps) => (
  <Card>
    <CardHeader>
      <CardTitle>Tóm tắt cấu hình</CardTitle>
      <p className="text-sm text-slate-500">
        Tham số dùng cho lần chạy lịch sử này (chỉ đọc).
      </p>
    </CardHeader>
    <CardContent>
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ["Chiến lược", strategy],
          ["Số dư ban đầu", formatCurrency(execution.initialBalance)],
          [METRICS.riskPerTrade, formatPercent(execution.riskPerTradePct)],
          ["Giới hạn lỗ trong ngày", formatPercent(execution.maxDailyLossPct)],
          [METRICS.maxDrawdown, formatPercent(execution.maxDrawdownPct)],
          ["Số vị thế mở tối đa", String(execution.maxOpenPositions)],
          ["Khối lượng vị thế tối đa", formatVolume(execution.maxPositionLots)],
          ["Số nến khởi động", String(execution.warmupBars)],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-slate-800 p-3">
            <dt className="text-xs uppercase text-slate-500">{label}</dt>
            <dd className="mt-1 text-sm font-medium tabular-nums text-slate-100">{value}</dd>
          </div>
        ))}
      </dl>
    </CardContent>
  </Card>
);
