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
import type { BacktestTradeRecord } from "@/domain";
import { formatCurrency, formatDurationBars } from "@/lib/format";
import { EmptyState } from "@/components/shared/States";
import { PNL_LABELS } from "@/lib/i18n/vi";

type TradeDistributionProps = {
  trades: BacktestTradeRecord[];
};

type DistributionChart = {
  id: string;
  title: string;
  ariaLabel: string;
  data: { label: string; count: number; tone?: "win" | "loss" | "flat" }[];
};

export const TradeDistribution = ({ trades }: TradeDistributionProps) => {
  if (!trades.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Phân phối giao dịch</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Phân phối giao dịch không khả dụng"
            description="Dữ liệu từng giao dịch không có trong báo cáo này. Phân phối cần bản ghi giao dịch riêng lẻ từ backtest engine."
          />
        </CardContent>
      </Card>
    );
  }

  const pnlBuckets = [
    { label: "< -$100", min: -Infinity, max: -100 },
    { label: "-$100 đến -$50", min: -100, max: -50 },
    { label: "-$50 đến $0", min: -50, max: 0 },
    { label: "$0 đến $50", min: 0, max: 50 },
    { label: "$50 đến $100", min: 50, max: 100 },
    { label: "> $100", min: 100, max: Infinity },
  ].map((b) => ({
    label: b.label,
    count: trades.filter((t) => t.netPnl > b.min && t.netPnl <= b.max).length,
  }));

  const winLoss = [
    { label: PNL_LABELS.profit, tone: "win" as const, count: trades.filter((t) => t.netPnl > 0).length },
    { label: PNL_LABELS.loss, tone: "loss" as const, count: trades.filter((t) => t.netPnl < 0).length },
    { label: PNL_LABELS.flat, tone: "flat" as const, count: trades.filter((t) => t.netPnl === 0).length },
  ];

  const durationBuckets = [
    { label: "≤ 4 nến", count: trades.filter((t) => t.barsHeld <= 4).length },
    { label: "5–12 nến", count: trades.filter((t) => t.barsHeld > 4 && t.barsHeld <= 12).length },
    { label: "13–24 nến", count: trades.filter((t) => t.barsHeld > 12 && t.barsHeld <= 24).length },
    { label: "> 24 nến", count: trades.filter((t) => t.barsHeld > 24).length },
  ];

  const avgDuration =
    trades.reduce((s, t) => s + t.barsHeld, 0) / trades.length;

  const charts: DistributionChart[] = [
    {
      id: "pnl",
      title: "Phân phối PnL",
      ariaLabel: "Biểu đồ phân phối PnL",
      data: pnlBuckets,
    },
    {
      id: "win-loss",
      title: "Thắng / thua",
      ariaLabel: "Biểu đồ thắng và thua",
      data: winLoss,
    },
    {
      id: "duration",
      title: "Thời lượng (nến)",
      ariaLabel: "Biểu đồ thời lượng giao dịch theo số nến",
      data: durationBuckets,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phân phối giao dịch</CardTitle>
        <p className="text-sm text-slate-500">
          Thời lượng TB: {formatDurationBars(Math.round(avgDuration))}
        </p>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-3">
        {charts.map(({ id, title, ariaLabel, data }) => (
          <div key={id}>
            <h4 className="mb-2 text-xs font-medium uppercase text-slate-500">{title}</h4>
            <div className="h-48 w-full" role="img" aria-label={ariaLabel}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="label" stroke="#64748b" fontSize={10} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis stroke="#64748b" fontSize={11} width={28} />
                  <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", color: "#0f172a" }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.map((entry) => (
                      <Cell
                        key={entry.label}
                        fill={
                          id === "win-loss"
                            ? entry.tone === "win"
                              ? "#059669"
                              : entry.tone === "loss"
                                ? "#e11d48"
                                : "#64748b"
                            : "#0284c7"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <ul className="mt-2 space-y-1 text-xs text-slate-500">
              {data.map((d) => (
                <li key={d.label}>
                  {d.label}: {d.count} giao dịch
                </li>
              ))}
            </ul>
          </div>
        ))}
      </CardContent>
      <CardContent className="border-t border-slate-200 pt-4">
        <p className="text-xs text-slate-500">
          Khoảng PnL mẫu: {formatCurrency(Math.min(...trades.map((t) => t.netPnl)))} đến{" "}
          {formatCurrency(Math.max(...trades.map((t) => t.netPnl)))}
        </p>
      </CardContent>
    </Card>
  );
};
