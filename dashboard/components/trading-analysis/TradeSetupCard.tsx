"use client";

import { PriceRelationshipBar } from "@/components/trading-analysis/PriceRelationshipBar";
import type { MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type TradeSetupCardProps = {
  analysis: MultiTimeframeAnalysis;
};

export const TradeSetupCard = ({ analysis }: TradeSetupCardProps) => {
  const setup = analysis.setup;
  const hasSetup = hasDirectionalSetup(analysis);

  if (!hasSetup || !setup) {
    return (
      <section
        className="surface-card flex h-full min-h-0 flex-col px-5 py-4"
        aria-label={L.setupTitle}
      >
        <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
          {L.setupTitle}
        </h3>
        <p className="mt-3 text-[14px] text-[var(--foreground-secondary)]">
          {L.noDirectionalSetup}
        </p>
      </section>
    );
  }

  const volume = analysis.sizing?.normalizedVolume;
  const tp1 = setup.takeProfits.find((t) => t.level === 1);
  const otherTps = setup.takeProfits.filter((t) => t.level !== 1);
  const signalTone =
    analysis.finalSignal === "LONG"
      ? "text-[var(--positive)] bg-[var(--positive-subtle)]"
      : analysis.finalSignal === "SHORT"
        ? "text-[var(--negative)] bg-[var(--negative-subtle)]"
        : "text-[var(--muted)] bg-[var(--surface-subtle)]";

  return (
    <section
      className="surface-card flex h-full min-h-0 flex-col px-5 py-4"
      aria-label={L.setupTitle}
    >
      <div className="flex shrink-0 items-center justify-between gap-2">
        <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
          {L.setupTitle}
        </h3>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[12px] font-bold uppercase",
            signalTone,
          )}
        >
          {analysis.finalSignal}
        </span>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <MetricRow
          label={L.entryZone}
          value={
            setup.entryZoneLow != null && setup.entryZoneHigh != null
              ? `${formatNumber(setup.entryZoneLow, 2)} – ${formatNumber(setup.entryZoneHigh, 2)}`
              : L.dash
          }
          emphasize
        />
        <MetricRow
          label={L.currentPrice}
          value={
            analysis.currentPrice == null
              ? L.dash
              : formatNumber(analysis.currentPrice, 2)
          }
        />
        <MetricRow
          label={L.stopLoss}
          value={
            setup.stopLoss == null ? L.dash : formatNumber(setup.stopLoss, 2)
          }
        />

        {tp1 ? (
          <div className="rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-3 py-2.5">
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                  TP1
                </p>
                <p className="mt-0.5 text-[12px] font-semibold tracking-wide text-[var(--positive)] uppercase">
                  {L.executionTarget}
                </p>
              </div>
              <p className="text-[17px] font-semibold tabular-nums text-[var(--foreground)]">
                {formatNumber(tp1.price, 2)}
              </p>
            </div>
          </div>
        ) : null}

        {otherTps.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {otherTps.map((tp) => (
              <div key={tp.level} className="min-w-0">
                <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                  TP{tp.level}
                </p>
                <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground-secondary)]">
                  {formatNumber(tp.price, 2)}
                </p>
                <p className="mt-0.5 text-[12px] text-[var(--muted)]">
                  {L.analysisTargetOnly}
                </p>
              </div>
            ))}
          </div>
        ) : null}

        <MetricRow
          label={L.volume}
          value={
            volume == null ? L.dash : `${formatNumber(volume, 2)} ${L.lot}`
          }
        />

        <PriceRelationshipBar analysis={analysis} />
      </div>
    </section>
  );
};

const MetricRow = ({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) => (
  <div className="flex min-w-0 items-start justify-between gap-3">
    <p className="shrink-0 pt-0.5 text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
      {label}
    </p>
    <p
      className={cn(
        "min-w-0 text-right font-semibold break-words tabular-nums text-[var(--foreground)]",
        emphasize ? "text-[15px]" : "text-[15px]",
      )}
    >
      {value}
    </p>
  </div>
);
