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
      <section className="surface-card h-full px-5 py-4" aria-label={L.setupTitle}>
        <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
          {L.setupTitle}
        </h3>
        <p className="mt-3 text-[14px] text-[var(--foreground-secondary)]">
          {L.noDirectionalSetup}
        </p>
      </section>
    );
  }

  const zone =
    setup.entryZoneLow != null && setup.entryZoneHigh != null
      ? `$${formatNumber(setup.entryZoneLow, 2)} – $${formatNumber(setup.entryZoneHigh, 2)}`
      : L.dash;
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
    <section className="surface-card h-full px-5 py-4" aria-label={L.setupTitle}>
      <div className="flex items-center justify-between gap-2">
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

      <div className="mt-4 space-y-4">
        <ValueBlock label={L.entryZone} value={zone} size="lg" />

        <div className="grid grid-cols-2 gap-4">
          <ValueBlock
            label={L.currentPrice}
            value={
              analysis.currentPrice == null
                ? L.dash
                : `$${formatNumber(analysis.currentPrice, 2)}`
            }
          />
          <ValueBlock
            label={L.stopLoss}
            value={
              setup.stopLoss == null ? L.dash : `$${formatNumber(setup.stopLoss, 2)}`
            }
          />
        </div>

        {tp1 ? (
          <div className="rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-3 py-3">
            <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
              TP1
            </p>
            <p className="mt-1 text-[18px] font-semibold tabular-nums text-[var(--foreground)]">
              ${formatNumber(tp1.price, 2)}
            </p>
            <p className="mt-0.5 text-[12px] font-semibold tracking-wide text-[var(--positive)] uppercase">
              {L.executionTarget}
            </p>
          </div>
        ) : null}

        {otherTps.length > 0 ? (
          <div className="grid grid-cols-2 gap-4">
            {otherTps.map((tp) => (
              <div key={tp.level}>
                <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                  TP{tp.level}
                </p>
                <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground-secondary)]">
                  ${formatNumber(tp.price, 2)}
                </p>
                <p className="mt-0.5 text-[12px] text-[var(--muted)]">
                  {L.analysisTargetOnly}
                </p>
              </div>
            ))}
          </div>
        ) : null}

        <ValueBlock
          label={L.volume}
          value={
            volume == null ? L.dash : `${formatNumber(volume, 2)} ${L.lot}`
          }
        />
      </div>

      <PriceRelationshipBar analysis={analysis} />
    </section>
  );
};

const ValueBlock = ({
  label,
  value,
  size = "md",
}: {
  label: string;
  value: string;
  size?: "md" | "lg";
}) => (
  <div>
    <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
      {label}
    </p>
    <p
      className={cn(
        "mt-1 font-semibold tabular-nums text-[var(--foreground)]",
        size === "lg" ? "text-[16px]" : "text-[15px]",
      )}
    >
      {value}
    </p>
  </div>
);
