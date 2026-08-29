import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { BacktestReport } from "@/domain";
import { BACKTEST_DATASET } from "@/lib/constants/backtest";
import { formatInteger } from "@/lib/format";

type BacktestInsufficientDataProps = {
  report: BacktestReport;
};

export const BacktestInsufficientData = ({ report }: BacktestInsufficientDataProps) => {
  const candles = report.dataset?.totalCandles ?? 0;

  return (
    <Card className="border-amber-900/50 bg-amber-950/15">
      <CardContent className="flex flex-col gap-4 py-8">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-400" aria-hidden />
          <div>
            <h3 className="text-lg font-semibold text-amber-100">Dữ liệu chưa đủ</h3>
            <p className="mt-2 text-sm leading-relaxed text-amber-100/80">
              {report.message ??
                "Dữ liệu lịch sử chưa đáp ứng mẫu tối thiểu để phân tích Backtest có ý nghĩa."}
            </p>
          </div>
        </div>
        <dl className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-amber-900/40 p-3">
            <dt className="text-xs uppercase text-amber-400/80">Số nến hiện có</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-amber-50">
              {formatInteger(candles)}
            </dd>
          </div>
          <div className="rounded-lg border border-amber-900/40 p-3">
            <dt className="text-xs uppercase text-amber-400/80">Tối thiểu yêu cầu</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-amber-50">
              {formatInteger(BACKTEST_DATASET.minMeaningfulCandles)}
            </dd>
          </div>
          <div className="rounded-lg border border-amber-900/40 p-3">
            <dt className="text-xs uppercase text-amber-400/80">Khuyến nghị</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-amber-50">
              {formatInteger(BACKTEST_DATASET.recommendedCandles)}+
            </dd>
          </div>
        </dl>
        <p className="text-sm font-medium text-amber-200/90">
          Các chỉ số hiệu suất được ẩn có chủ đích.
        </p>
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
          <p className="font-medium text-slate-300">Bước tiếp theo</p>
          <p className="mt-2">
            Xuất dữ liệu lịch sử XAUUSD M15 từ MT5 bằng công cụ export của trading-engine, sau đó
            chạy Backtest baseline:
          </p>
          <code className="mt-2 block rounded bg-slate-900 px-3 py-2 text-xs text-slate-300">
            python -m exness_bot.tools.export_history --symbol XAUUSD --timeframe M15
          </code>
        </div>
      </CardContent>
    </Card>
  );
};
