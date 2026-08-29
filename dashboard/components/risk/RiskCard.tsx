import type { RiskLimit } from "@/domain";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatVolume,
} from "@/lib/format";
import {
  getRiskLevel,
  RISK_LEVEL_LABELS,
  RISK_THRESHOLDS,
} from "@/lib/constants/risk";
import { UI } from "@/lib/i18n/vi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type RiskCardProps = {
  limit: RiskLimit;
};

const formatLimitValue = (limit: RiskLimit, value: number): string => {
  switch (limit.unit) {
    case "percent":
      return formatPercent(value);
    case "currency":
      return formatCurrency(value);
    case "lots":
      return formatVolume(value);
    default:
      return formatNumber(value, 0);
  }
};

export const RiskCard = ({ limit }: RiskCardProps) => {
  const usagePct =
    limit.configuredLimit > 0 ? (limit.currentValue / limit.configuredLimit) * 100 : 0;
  const level = getRiskLevel(usagePct);

  const levelVariant =
    level === "critical" ? "danger" : level === "warning" ? "warning" : "success";

  return (
    <Card
      className={cn(
        level === "critical" && "border-rose-300",
        level === "warning" && "border-amber-300",
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
        <CardTitle className="text-sm">{limit.label}</CardTitle>
        <Badge variant={levelVariant} className="normal-case">
          {RISK_LEVEL_LABELS[level]}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{UI.currentLimit}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatLimitValue(limit, limit.currentValue)}
            <span className="mx-2 text-slate-600">/</span>
            {formatLimitValue(limit, limit.configuredLimit)}
          </p>
        </div>

        <div>
          <div className="mb-1.5 flex justify-between text-xs text-slate-500">
            <span>{UI.utilization}</span>
            <span>
              {formatNumber(usagePct, 0)}% · {UI.riskWarnCrit(RISK_THRESHOLDS.normalMax, RISK_THRESHOLDS.warningMax)}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                level === "critical" && "bg-rose-500",
                level === "warning" && "bg-amber-500",
                level === "normal" && "bg-emerald-500",
              )}
              style={{ width: `${Math.min(usagePct, 100)}%` }}
              role="progressbar"
              aria-valuenow={Math.round(usagePct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={UI.riskUtilizationAria(limit.label, formatNumber(usagePct, 0))}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
