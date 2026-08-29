"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestRAnalysis } from "@/domain";
import { formatRMultiple } from "@/lib/format";
import { A11Y } from "@/lib/i18n/vi";

type RDistributionProps = {
  rAnalysis: BacktestRAnalysis | null;
};

const bucketRValues = (values: number[]) => {
  const buckets = new Map<string, number>();
  for (const r of values) {
    const key = r >= 0 ? `+${Math.floor(r)}R` : `${Math.ceil(r)}R`;
    buckets.set(key, (buckets.get(key) ?? 0) + 1);
  }
  return [...buckets.entries()]
    .map(([bucket, count]) => ({ bucket, count }))
    .sort((a, b) => {
      const parse = (s: string) => Number.parseInt(s.replace("R", ""), 10);
      return parse(a.bucket) - parse(b.bucket);
    });
};

export const RDistribution = ({ rAnalysis }: RDistributionProps) => {
  if (!rAnalysis?.rMultiples.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Phân tích hệ số R</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">
            Phân phối hệ số R không khả dụng cho báo cáo này.
          </p>
        </CardContent>
      </Card>
    );
  }

  const chartData = bucketRValues(rAnalysis.rMultiples);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phân tích hệ số R</CardTitle>
        <dl className="mt-2 grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ["Hệ số R trung bình", formatRMultiple(rAnalysis.averageR)],
            ["R khi thắng", formatRMultiple(rAnalysis.winningRAverage)],
            ["R khi thua", formatRMultiple(rAnalysis.losingRAverage)],
            ["R tốt nhất", formatRMultiple(rAnalysis.bestR)],
            ["R tệ nhất", formatRMultiple(rAnalysis.worstR)],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt>{label}</dt>
              <dd className="font-medium tabular-nums text-slate-300">{value}</dd>
            </div>
          ))}
        </dl>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full" role="img" aria-label={A11Y.rDistributionChart}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} width={32} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.bucket}
                    fill={entry.bucket.startsWith("+") || entry.bucket.startsWith("0") ? "#34d399" : "#fb7185"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          R = biên độ giá / khoảng cách cắt lỗ. Tính từ giá vào lệnh, giá thoát và cắt lỗ theo quy
          tắc engine.
        </p>
      </CardContent>
    </Card>
  );
};
