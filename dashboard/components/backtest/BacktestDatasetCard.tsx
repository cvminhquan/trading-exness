import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestDataset } from "@/domain";
import { BACKTEST_DATASET } from "@/lib/constants/backtest";
import { formatDateRange, formatInteger } from "@/lib/format";
import { QUALITY_STATUS_LABELS } from "@/lib/i18n/vi";

const QUALITY_VARIANT: Record<
  BacktestDataset["qualityStatus"],
  "success" | "warning" | "danger"
> = {
  VALID: "success",
  WARNING: "warning",
  INSUFFICIENT: "danger",
};

type BacktestDatasetCardProps = {
  dataset: BacktestDataset;
  symbol: string;
  timeframe: string;
};

export const BacktestDatasetCard = ({
  dataset,
  symbol,
  timeframe,
}: BacktestDatasetCardProps) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between gap-3">
      <CardTitle>Bộ dữ liệu</CardTitle>
      <Badge variant={QUALITY_VARIANT[dataset.qualityStatus]}>
        {QUALITY_STATUS_LABELS[dataset.qualityStatus]}
      </Badge>
    </CardHeader>
    <CardContent>
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ["Symbol", symbol],
          ["Khung thời gian", timeframe],
          [
            "Khoảng thời gian",
            formatDateRange(dataset.startTimestamp, dataset.endTimestamp),
          ],
          ["Số nến", `${formatInteger(dataset.totalCandles)}+`],
          ["Thời lượng", `${formatInteger(dataset.durationDays)} ngày`],
          ["Múi giờ", dataset.timezone],
          ["Đã sắp xếp", dataset.isSorted ? "Có" : "Không"],
          ["OHLC hợp lệ", dataset.isValidOhlc ? "Có" : "Không"],
          ["Mẫu có ý nghĩa", dataset.isMeaningful ? "Có" : "Không"],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-slate-800 p-3">
            <dt className="text-xs uppercase text-slate-500">{label}</dt>
            <dd className="mt-1 text-sm text-slate-200">{value}</dd>
          </div>
        ))}
      </dl>
      {!dataset.isMeaningful ? (
        <p className="mt-4 rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100/90">
          Tối thiểu yêu cầu: {formatInteger(BACKTEST_DATASET.minMeaningfulCandles)} nến.
          Khuyến nghị: {formatInteger(BACKTEST_DATASET.recommendedCandles)}+ nến.
        </p>
      ) : null}
    </CardContent>
  </Card>
);
