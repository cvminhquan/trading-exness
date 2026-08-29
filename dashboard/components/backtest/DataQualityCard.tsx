import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestDataset } from "@/domain";
import { BACKTEST_DATASET } from "@/lib/constants/backtest";
import { formatInteger } from "@/lib/format";
import { QUALITY_STATUS_LABELS } from "@/lib/i18n/vi";

const QUALITY_VARIANT: Record<
  BacktestDataset["qualityStatus"],
  "success" | "warning" | "danger"
> = {
  VALID: "success",
  WARNING: "warning",
  INSUFFICIENT: "danger",
};

type DataQualityCardProps = {
  dataset: BacktestDataset;
};

export const DataQualityCard = ({ dataset }: DataQualityCardProps) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between gap-3">
      <CardTitle>Chất lượng dữ liệu</CardTitle>
      <Badge variant={QUALITY_VARIANT[dataset.qualityStatus]}>
        {QUALITY_STATUS_LABELS[dataset.qualityStatus]}
      </Badge>
    </CardHeader>
    <CardContent>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ["Tổng số nến", formatInteger(dataset.totalCandles)],
          ["Timestamp trùng lặp", formatInteger(dataset.duplicateTimestamps)],
          ["Khoảng thiếu", formatInteger(dataset.missingPeriods)],
          ["Nến thiếu (tổng)", formatInteger(dataset.missingBarsTotal)],
          ["Khoảng trống cuối tuần", formatInteger(dataset.weekendGaps)],
          ["Khoảng trống phiên", formatInteger(dataset.sessionGaps)],
          ["Múi giờ", dataset.timezone],
          ["Đã sắp xếp", dataset.isSorted ? "Có" : "Không"],
          ["OHLC hợp lệ", dataset.isValidOhlc ? "Có" : "Không"],
          ["Mẫu có ý nghĩa", dataset.isMeaningful ? "Có" : "Không"],
          ["Tối thiểu yêu cầu", formatInteger(dataset.minRequiredCandles)],
          ["Khuyến nghị", `${formatInteger(dataset.recommendedCandles)}+`],
        ].map(([label, value]) => (
          <div key={String(label)} className="flex justify-between gap-4 border-b border-slate-800 py-2 text-sm">
            <dt className="text-slate-500">{label}</dt>
            <dd className="tabular-nums text-slate-200">{value}</dd>
          </div>
        ))}
      </dl>
      {dataset.qualityStatus === "INSUFFICIENT" ? (
        <p className="mt-4 text-sm text-amber-200/90">
          Bộ dữ liệu dưới {formatInteger(BACKTEST_DATASET.minMeaningfulCandles)} nến — kết quả
          không thể được xếp loại là bằng chứng edge có ý nghĩa.
        </p>
      ) : null}
    </CardContent>
  </Card>
);
