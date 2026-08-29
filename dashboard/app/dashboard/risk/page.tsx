"use client";

import { MetricCard } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { MetricGridSkeleton } from "@/components/shared/Skeletons";
import { RiskCard } from "@/components/risk/RiskCard";
import type { RiskCategory, RiskLimit } from "@/domain";
import { formatCurrency, formatPercent } from "@/lib/format";
import { METRICS, NAV, RISK_GROUP_LABELS, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { useRiskSnapshot } from "@/queries/use-trading-queries";

const GROUP_ORDER: RiskCategory[] = ["account", "trade", "daily", "drawdown", "exposure"];

const groupLimits = (limits: RiskLimit[]) =>
  GROUP_ORDER.map((category) => ({
    category,
    label: RISK_GROUP_LABELS[category],
    items: limits.filter((l) => l.category === category),
  })).filter((group) => group.items.length > 0);

export default function RiskPage() {
  const { data, isLoading, isError, error, refetch } = useRiskSnapshot();

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.risk.label}
        description={NAV.risk.description}
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        onRetry={() => void refetch()}
        loadingFallback={<MetricGridSkeleton count={6} />}
        section={SECTION_LABELS.risk}
      >
        {data ? (
          <>
            <section className="grid gap-4 sm:grid-cols-2">
              <MetricCard label={METRICS.accountEquity} value={formatCurrency(data.equity)} />
              <MetricCard
                label={METRICS.riskPerTrade}
                value={formatPercent(data.riskPerTradePct)}
                hint={UI.riskPerTradeHint}
              />
            </section>

            {groupLimits(data.limits).map((group) => (
              <section key={group.category} aria-label={group.label} className="space-y-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
                  {group.label}
                </h2>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {group.items.map((limit) => (
                    <RiskCard key={limit.key} limit={limit} />
                  ))}
                </div>
              </section>
            ))}
          </>
        ) : null}
      </QueryState>
    </div>
  );
}
