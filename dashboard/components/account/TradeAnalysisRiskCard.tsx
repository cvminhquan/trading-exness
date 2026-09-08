"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import { ACCOUNT_OVERVIEW, METRICS } from "@/lib/i18n/vi";
import { estimateRiskSizing } from "@/lib/risk/sizing";
import { cn } from "@/lib/utils";

type TradeAnalysisRiskCardProps = {
  equity: number | null | undefined;
  riskPerTradePct: number;
  brokerMinLot?: number;
  stopDistancePrice?: number;
  contractSize?: number;
};

/**
 * Phân tích rủi ro chỉ đọc.
 * Tài khoản nhỏ (~$10.5) vẫn được mở 0.01 lot (min broker);
 * hiển thị rủi ro thực tế và số tiền / % thiếu so với cấu hình.
 */
export const TradeAnalysisRiskCard = ({
  equity,
  riskPerTradePct,
  brokerMinLot = 0.01,
  stopDistancePrice = 5,
  contractSize = 100,
}: TradeAnalysisRiskCardProps) => {
  if (equity == null || Number.isNaN(equity)) {
    return null;
  }

  const sizing = estimateRiskSizing({
    equity,
    riskPerTradePct,
    brokerMinLot,
    stopDistancePrice,
    contractSize,
  });
  if (!sizing) return null;

  return (
    <Card aria-label={ACCOUNT_OVERVIEW.analysisTitle}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            {ACCOUNT_OVERVIEW.analysisTitle}
          </p>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-semibold",
              sizing.minLotAllowed
                ? "bg-emerald-50 text-emerald-700"
                : "bg-rose-50 text-rose-700",
            )}
          >
            {ACCOUNT_OVERVIEW.minLotOpenable}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-[11px] text-slate-500">{METRICS.riskPerTrade}</p>
            <p className="font-medium tabular-nums">{formatPercent(riskPerTradePct)}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-500">{ACCOUNT_OVERVIEW.riskBudget}</p>
            <p className="font-medium tabular-nums">{formatCurrency(sizing.riskBudget)}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-500">{ACCOUNT_OVERVIEW.brokerMinimum}</p>
            <p className="font-medium tabular-nums">{formatNumber(sizing.brokerMinLot, 2)}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-500">{ACCOUNT_OVERVIEW.calculatedLot}</p>
            <p className="font-medium tabular-nums">{formatNumber(sizing.calculatedLot, 3)}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-500">{ACCOUNT_OVERVIEW.riskAtMinLot}</p>
            <p className="font-medium tabular-nums">{formatCurrency(sizing.riskAtMinLot)}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-500">{ACCOUNT_OVERVIEW.riskPctAtMinLot}</p>
            <p className="font-medium tabular-nums">
              {formatPercent(sizing.riskPctAtMinLot)}
            </p>
          </div>
        </div>

        {!sizing.withinConfiguredRisk ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
            <p className="font-medium">{ACCOUNT_OVERVIEW.shortfallLabel}</p>
            <p className="mt-0.5 tabular-nums">
              {formatCurrency(sizing.shortfall)} · {ACCOUNT_OVERVIEW.shortfallHint}
            </p>
          </div>
        ) : (
          <p className="text-xs leading-relaxed text-slate-500">{ACCOUNT_OVERVIEW.reasonOk}</p>
        )}
      </CardContent>
    </Card>
  );
};
