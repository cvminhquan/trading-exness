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
        <h3 className="text-[11px] font-bold tracking-[0.08em] text-[var(--muted)] uppercase">
          {L.setupTitle}
        </h3>
        <p className="mt-2 text-[13px] text-[var(--foreground-secondary)]">
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
      <h3 className="text-[11px] font-bold tracking-[0.08em] text-[var(--muted)] uppercase">
        {L.setupTitle}
      </h3>

      <div className="mt-3.5 space-y-3.5">
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
            <p className="mt-0.5 text-right text-[11px] font-medium text-[var(--muted)]">
              {L.slDistance}: {formatNumber(slDistancePts, 2)}
              {slDistancePct != null
                ? ` (${formatNumber(slDistancePct, 2)}%)`
                : ""}
            </p>
          ) : null}
        </div>

        <div>
          <p className="text-[11px] font-bold tracking-[0.06em] text-[var(--muted)] uppercase">
            {L.takeProfit}
          </p>
          {tp1 ? (
            <div className="mt-2 flex items-center justify-between gap-3 rounded-[var(--radius-control)] border border-[var(--positive)]/20 bg-[var(--positive-subtle)] px-3 py-2.5">
              <div>
                <p className="text-[12px] font-bold tracking-wide text-[var(--foreground)] uppercase">
                  TP1
                </p>
                <span className="mt-0.5 inline-flex rounded-full bg-[var(--positive)]/15 px-1.5 py-px text-[10px] font-bold tracking-wide text-[var(--positive)] uppercase">
                  {L.executionTarget}
                </span>
              </div>
              <p className="text-[17px] font-bold tabular-nums text-[var(--foreground)]">
                {formatNumber(tp1.price, 2)}
              </p>
            </div>
          ) : (
            <p className="mt-1.5 text-[13px] text-[var(--muted)]">{L.dash}</p>
          )}
          {otherTps.map((tp) => (
            <div
              key={tp.level}
              className="mt-2 flex items-baseline justify-between gap-3 border-b border-[var(--border)]/70 px-1 pb-2 last:border-0"
            >
              <div>
                <p className="text-[12px] font-semibold text-[var(--foreground-secondary)]">
                  TP{tp.level}
                </p>
                <p className="text-[10px] font-medium tracking-wide text-[var(--muted)] uppercase">
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
          value={tp1?.rr == null ? L.dash : `1 : ${formatNumber(tp1.rr, 1)}`}
          emphasize
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
  <div className="flex min-w-0 items-baseline justify-between gap-3">
    <p className="shrink-0 text-[12px] font-medium text-[var(--muted)]">
      {label}
    </p>
    <p
      className={cn(
        "min-w-0 text-right break-words tabular-nums tracking-tight text-[var(--foreground)]",
        emphasize ? "text-[15px] font-bold" : "text-[14px] font-semibold",
      )}
    >
      {value}
    </p>
  </div>
);
