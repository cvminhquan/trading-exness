"use client";

import type { ReactNode } from "react";
import type { AccountOverview } from "@/domain";
import { PnLValue } from "@/components/shared/PnLValue";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/format";
import { ACCOUNT_OVERVIEW, METRICS } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type AccountOverviewSectionProps = {
  overview: AccountOverview;
};

const Stat = ({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) => (
  <div className="min-w-0">
    <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
      {label}
    </p>
    <div className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">
      {children}
    </div>
  </div>
);

export const AccountOverviewSection = ({
  overview,
}: AccountOverviewSectionProps) => {
  const unavailable =
    overview.status === "DISCONNECTED" || overview.status === "UNAVAILABLE";

  if (unavailable) {
    return (
      <section aria-label={ACCOUNT_OVERVIEW.title} className="py-2">
        <p className="text-sm text-rose-800">{ACCOUNT_OVERVIEW.dataUnavailable}</p>
        {overview.message ? (
          <p className="mt-0.5 text-xs text-slate-500">{overview.message}</p>
        ) : null}
      </section>
    );
  }

  const returnLabel =
    overview.dailyReturnAvailable && overview.dailyReturnPct != null
      ? formatPercent(overview.dailyReturnPct)
      : ACCOUNT_OVERVIEW.returnUnavailable;

  return (
    <section
      className="border-t border-slate-200 pt-3"
      aria-label={ACCOUNT_OVERVIEW.title}
    >
      {overview.status === "STALE" && overview.message ? (
        <p className="mb-2 text-xs text-amber-800" role="status">
          {overview.message}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label={METRICS.equity}>{formatCurrency(overview.equity)}</Stat>
        <Stat label={METRICS.balance}>{formatCurrency(overview.balance)}</Stat>
        <Stat label={ACCOUNT_OVERVIEW.todayPnl}>
          <PnLValue
            value={overview.totalPnlToday}
            showIcon={false}
            className="text-sm"
          />
        </Stat>
        <Stat label={METRICS.marginLevel}>
          {overview.marginLevel == null
            ? "—"
            : `${formatNumber(overview.marginLevel, 2)}%`}
        </Stat>
        <Stat label={METRICS.openPositions}>
          {overview.openPositionsCount}
        </Stat>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-slate-500">
        <span>
          {METRICS.usedMargin}{" "}
          <span className="tabular-nums text-slate-700">
            {overview.margin == null ? "—" : formatCurrency(overview.margin)}
          </span>
        </span>
        <span>
          {ACCOUNT_OVERVIEW.unrealized}{" "}
          <span className="tabular-nums text-slate-700">
            {formatSignedCurrency(overview.unrealizedPnl)}
          </span>
        </span>
        <span>
          {ACCOUNT_OVERVIEW.realized}{" "}
          <span className="tabular-nums text-slate-700">
            {formatSignedCurrency(overview.realizedPnlToday)}
          </span>
        </span>
        <span
          title={
            overview.dailyReturnAvailable
              ? undefined
              : ACCOUNT_OVERVIEW.returnUnavailableHint
          }
        >
          {ACCOUNT_OVERVIEW.returnLabel}{" "}
          <span
            className={cn(
              "tabular-nums",
              overview.dailyReturnAvailable ? "text-slate-700" : "text-slate-400",
            )}
          >
            {returnLabel}
          </span>
        </span>
      </div>
    </section>
  );
};
