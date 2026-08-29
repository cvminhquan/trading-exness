"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { formatPercent } from "@/lib/format";
import { NAV, SECTION_LABELS, SETTINGS, UI } from "@/lib/i18n/vi";
import { useSystemSettings } from "@/queries/use-trading-queries";

type SettingKey = keyof typeof SETTINGS.labels;

const GROUPS: { title: string; keys: SettingKey[] }[] = [
  {
    title: SETTINGS.groups.broker,
    keys: ["broker"],
  },
  {
    title: SETTINGS.groups.tradingMode,
    keys: ["tradingMode"],
  },
  {
    title: SETTINGS.groups.market,
    keys: ["symbol", "timeframe"],
  },
  {
    title: SETTINGS.groups.strategy,
    keys: ["strategy"],
  },
  {
    title: SETTINGS.groups.risk,
    keys: ["riskPerTrade", "maxDailyLoss", "maxDrawdown", "maxOpenPositions"],
  },
];

export default function SettingsPage() {
  const { data, isLoading, isError, error, refetch } = useSystemSettings();

  const rows: { key: SettingKey; value: string }[] = data
    ? [
        { key: "tradingMode", value: data.tradingMode },
        { key: "broker", value: data.broker },
        { key: "symbol", value: data.symbol },
        { key: "timeframe", value: data.timeframe },
        { key: "strategy", value: data.strategy },
        { key: "riskPerTrade", value: formatPercent(data.riskPerTradePct) },
        { key: "maxDailyLoss", value: formatPercent(data.maxDailyLossPct) },
        { key: "maxDrawdown", value: formatPercent(data.maxDrawdownPct) },
        { key: "maxOpenPositions", value: String(data.maxOpenPositions) },
      ]
    : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.settings.label}
        description={NAV.settings.description}
        badge={
          <Badge variant="default" className="normal-case">
            {UI.readOnly}
          </Badge>
        }
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={5} />}
        section={SECTION_LABELS.settings}
      >
        <div className="space-y-4">
          {GROUPS.map((group) => (
            <Card key={group.title}>
              <CardHeader>
                <CardTitle>{group.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="divide-y divide-slate-800">
                  {rows
                    .filter((row) => group.keys.includes(row.key))
                    .map((row) => (
                      <div
                        key={row.key}
                        className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <dt className="text-sm text-slate-400">{SETTINGS.labels[row.key]}</dt>
                        <dd className="font-medium tabular-nums text-slate-100">{row.value}</dd>
                      </div>
                    ))}
                </dl>
              </CardContent>
            </Card>
          ))}
          <p className="text-xs text-slate-500">{UI.settingsConfigDisabled}</p>
        </div>
      </QueryState>
    </div>
  );
}
