"use client";

import type { ReactNode } from "react";
import type { AccountOverview } from "@/domain";
import { PnLValue } from "@/components/shared/PnLValue";
import {
  formatMoney,
  formatNumber,
  formatSignedPercent,
} from "@/lib/format";
import { ACCOUNT_OVERVIEW, METRICS } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type AccountOverviewSectionProps = {
  overview: AccountOverview;
};

const Stat = ({
  label,
  children,
  emphasize,
}: {
  label: string;
  children: ReactNode;
  emphasize?: boolean;
}) => (
  <div className="min-w-0">
    <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
      {label}
    </p>
    <div
      className={cn(
        "mt-1 leading-tight font-semibold tabular-nums text-[var(--foreground)]",
        emphasize ? "text-[22px]" : "text-[20px]",
      )}
    >
      {children}
    </div>
  </div>
);

export const AccountOverviewSection = ({
  overview,
}: AccountOverviewSectionProps) => {
  const unavailable =
    overview.status === "DISCONNECTED" || overview.status === "UNAVAILABLE";
  const currency = overview.currency ?? "USD";

  if (unavailable) {
    return (
      <section
        aria-label={ACCOUNT_OVERVIEW.title}
        className="surface-card px-5 py-4"
      >
        <p className="text-[14px] font-medium text-[var(--negative)]">
          {ACCOUNT_OVERVIEW.dataUnavailable}
        </p>
        {overview.message ? (
          <p className="mt-1 text-[13px] text-[var(--muted)]">{overview.message}</p>
        ) : null}
      </section>
    );
  }

  return (
    <section
      className="surface-card px-5 py-4"
      aria-label={ACCOUNT_OVERVIEW.title}
    >
      {overview.status === "STALE" && overview.message ? (
        <p className="mb-3 text-[13px] text-[var(--warning)]" role="status">
          {overview.message}
        </p>
      ) : null}

      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5 lg:divide-x lg:divide-[var(--border)]">
          <div className="lg:pr-5">
            <Stat label={ACCOUNT_OVERVIEW.todayPnl} emphasize>
              <div>
                <PnLValue
                  value={overview.totalPnlToday}
                  showIcon={false}
                  className="text-[22px] font-semibold"
                />
                {overview.dailyReturnAvailable &&
                overview.dailyReturnPct != null ? (
                  <p
                    className={cn(
                      "mt-0.5 text-[13px] font-semibold tabular-nums",
                      overview.dailyReturnPct > 0 && "text-[var(--positive)]",
                      overview.dailyReturnPct < 0 && "text-[var(--negative)]",
                      overview.dailyReturnPct === 0 && "text-[var(--muted)]",
                    )}
                  >
                    {formatSignedPercent(overview.dailyReturnPct)}
                  </p>
                ) : null}
              </div>
            </Stat>
          </div>
          <div className="lg:px-5">
            <Stat label={METRICS.equity}>
              {formatMoney(overview.equity, currency)}
            </Stat>
          </div>
          <div className="lg:px-5">
            <Stat label={METRICS.balance}>
              {formatMoney(overview.balance, currency)}
            </Stat>
          </div>
          <div className="lg:px-5">
            <Stat label={METRICS.marginLevel}>
              {overview.marginLevel == null
                ? "—"
                : `${formatNumber(overview.marginLevel, 2)}%`}
            </Stat>
          </div>
          <div className="lg:pl-5">
            <Stat label={METRICS.openPositions}>
              {overview.openPositionsCount}
            </Stat>
          </div>
        </div>

        <div className="shrink-0 space-y-1.5 border-t border-[var(--border)] pt-3 text-[13px] xl:border-t-0 xl:border-l xl:pt-0 xl:pl-5">
          <p className="text-[var(--muted)]">
            {METRICS.usedMargin}{" "}
            <span className="font-semibold tabular-nums text-[var(--foreground-secondary)]">
              {formatMoney(overview.margin, currency)}
            </span>
          </p>
          <p className="text-[var(--muted)]">
            {ACCOUNT_OVERVIEW.unrealized}{" "}
            <PnLValue
              value={overview.unrealizedPnl}
              showIcon={false}
              className="inline text-[13px] font-semibold"
            />
          </p>
          <p className="text-[var(--muted)]">
            {ACCOUNT_OVERVIEW.realized}{" "}
            <PnLValue
              value={overview.realizedPnlToday}
              showIcon={false}
              className="inline text-[13px] font-semibold"
            />
          </p>
        </div>
      </div>
    </section>
  );
};
