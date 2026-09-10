"use client";

import type { MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type TradePlanSectionProps = {
  analysis: MultiTimeframeAnalysis;
};

/** Nested trade-plan block — no duplicate signal / current price / S/R. */
export const TradePlanSection = ({ analysis }: TradePlanSectionProps) => {
  const setup = analysis.setup;
  const hasSetup = hasDirectionalSetup(analysis);

  if (!hasSetup || !setup) {
    return (
      <section aria-label={L.setupTitle}>
        <h3 className="text-[13px] font-semibold tracking-wide text-[var(--muted)] uppercase">
          {L.setupTitle}
        </h3>
        <p className="mt-2 text-[14px] text-[var(--foreground-secondary)]">
          {L.noDirectionalSetup}
        </p>
      </section>
    );
  }

  const volume = analysis.sizing?.normalizedVolume;
  const tp1 = setup.takeProfits.find((t) => t.level === 1);
  const otherTps = setup.takeProfits.filter((t) => t.level !== 1);
  const zoneLow = setup.entryZoneLow;
  const zoneHigh = setup.entryZoneHigh;
  const entryMid =
    zoneLow != null && zoneHigh != null ? (zoneLow + zoneHigh) / 2 : null;
  const sl = setup.stopLoss;
  const slDistancePts =
    entryMid != null && sl != null ? Math.abs(sl - entryMid) : null;
  const slDistancePct =
    entryMid != null && entryMid !== 0 && slDistancePts != null
      ? (slDistancePts / Math.abs(entryMid)) * 100
      : null;

  return (
    <section aria-label={L.setupTitle}>
      <h3 className="text-[13px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        {L.setupTitle}
      </h3>

      <div className="mt-3 space-y-3">
        <PlanRow
          label={L.entryZone}
          value={
            zoneLow != null && zoneHigh != null
              ? `${formatNumber(Math.min(zoneLow, zoneHigh), 2)} – ${formatNumber(Math.max(zoneLow, zoneHigh), 2)}`
              : L.noEntryZone
          }
          emphasize
        />

        <div>
          <PlanRow
            label={L.stopLoss}
            value={sl == null ? L.dash : formatNumber(sl, 2)}
          />
          {slDistancePts != null ? (
            <p className="mt-0.5 text-right text-[12px] text-[var(--muted)]">
              {L.slDistance}: {formatNumber(slDistancePts, 2)}
              {slDistancePct != null
                ? ` (${formatNumber(slDistancePct, 2)}%)`
                : ""}
            </p>
          ) : null}
        </div>

        <div>
          <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
            {L.takeProfit}
          </p>
          {tp1 ? (
            <div className="mt-1.5 flex items-baseline justify-between gap-3 rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-3 py-2">
              <div>
                <p className="text-[12px] font-bold tracking-wide text-[var(--foreground)] uppercase">
                  TP1
                </p>
                <p className="text-[11px] font-semibold tracking-wide text-[var(--positive)] uppercase">
                  {L.executionTarget}
                </p>
              </div>
              <p className="text-[16px] font-semibold tabular-nums text-[var(--foreground)]">
                {formatNumber(tp1.price, 2)}
              </p>
            </div>
          ) : (
            <p className="mt-1 text-[14px] text-[var(--muted)]">{L.dash}</p>
          )}
          {otherTps.map((tp) => (
            <div
              key={tp.level}
              className="mt-1.5 flex items-baseline justify-between gap-3 px-1"
            >
              <div>
                <p className="text-[12px] font-semibold text-[var(--foreground-secondary)]">
                  TP{tp.level}
                </p>
                <p className="text-[11px] text-[var(--muted)]">
                  {L.analysisTargetOnly}
                </p>
              </div>
              <p className="text-[14px] font-semibold tabular-nums text-[var(--foreground-secondary)]">
                {formatNumber(tp.price, 2)}
              </p>
            </div>
          ))}
        </div>

        <PlanRow
          label={L.rrTp1}
          value={
            tp1?.rr == null ? L.dash : `1 : ${formatNumber(tp1.rr, 1)}`
          }
        />

        <PlanRow
          label={L.proposedVolume}
          value={
            volume == null ? L.dash : `${formatNumber(volume, 2)} ${L.lot}`
          }
          emphasize
        />
      </div>
    </section>
  );
};

const PlanRow = ({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) => (
  <div className="flex min-w-0 items-start justify-between gap-3">
    <p className="shrink-0 pt-0.5 text-[12px] font-medium text-[var(--muted)]">
      {label}
    </p>
    <p
      className={cn(
        "min-w-0 text-right break-words tabular-nums text-[var(--foreground)]",
        emphasize ? "text-[15px] font-semibold" : "text-[14px] font-semibold",
      )}
    >
      {value}
    </p>
  </div>
);
