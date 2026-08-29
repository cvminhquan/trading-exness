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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MonthlyPerformance } from "@/domain";
import { PnLValue } from "@/components/shared/PnLValue";
import { formatCurrency, formatPercent } from "@/lib/format";
import { A11Y, METRICS } from "@/lib/i18n/vi";

type MonthlyPerformanceSectionProps = {
  data: MonthlyPerformance[];
};

export const MonthlyPerformanceSection = ({ data }: MonthlyPerformanceSectionProps) => {
  if (!data.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hiệu suất theo tháng</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">
            Không có phân tích theo tháng cho báo cáo này.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-amber-900/30">
      <CardHeader>
        <CardTitle>Hiệu suất theo tháng</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tháng</TableHead>
                <TableHead className="text-right">PnL ròng</TableHead>
                <TableHead className="text-right">{METRICS.returnPct}</TableHead>
                <TableHead className="text-right">Giao dịch</TableHead>
                <TableHead className="text-right">{METRICS.winRate}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <TableRow key={row.month}>
                  <TableCell className="font-medium">{row.month}</TableCell>
                  <TableCell className="text-right">
                    <PnLValue value={row.netPnl} showIcon={false} className="text-sm" />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.returnPct !== null ? formatPercent(row.returnPct) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.trades}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPercent(row.winRate)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="h-56 w-full" role="img" aria-label={A11Y.monthlyPnlChart}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
              <YAxis
                tickFormatter={(v: number) => formatCurrency(v)}
                stroke="#64748b"
                fontSize={11}
                width={72}
              />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
                formatter={(value, name) => [
                  name === "netPnl" ? formatCurrency(Number(value)) : value,
                  name === "netPnl" ? "PnL ròng" : "Giao dịch",
                ]}
              />
              <Bar dataKey="netPnl" radius={[4, 4, 0, 0]}>
                {data.map((entry) => (
                  <Cell
                    key={entry.month}
                    fill={entry.netPnl >= 0 ? "#34d399" : "#fb7185"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};
