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
      <section aria-label={L.setupTitle}>
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {L.setupTitle}
        </h3>
        <p className="mt-2 text-sm text-slate-600">{L.noDirectionalSetup}</p>
      </section>
    );
  }

  const zone =
    setup.entryZoneLow != null && setup.entryZoneHigh != null
      ? `${formatNumber(setup.entryZoneLow, 2)} – ${formatNumber(setup.entryZoneHigh, 2)}`
      : L.dash;
  const volume = analysis.sizing?.normalizedVolume;

  return (
    <section aria-label={L.setupTitle}>
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {L.setupTitle}
      </h3>

      <dl className="mt-2 space-y-1.5 text-sm">
        <Row label={L.direction} value={analysis.finalSignal} emphasize />
        <Row label={L.entryZone} value={zone} />
        <Row
          label={L.currentPrice}
          value={
            analysis.currentPrice == null
              ? L.dash
              : formatNumber(analysis.currentPrice, 2)
          }
        />
        <Row
          label={L.stopLoss}
          value={setup.stopLoss == null ? L.dash : formatNumber(setup.stopLoss, 2)}
        />
      </dl>

      <ul className="mt-2 space-y-1">
        {setup.takeProfits.map((tp) => {
          const isTp1 = tp.level === 1;
          return (
            <li
              key={tp.level}
              className="flex items-baseline justify-between gap-2 text-sm"
            >
              <span className="text-slate-500">
                TP{tp.level}
                <span className="ml-1.5 text-[10px] uppercase tracking-wide text-slate-400">
                  {isTp1 ? L.executionTarget : L.analysisTargetOnly}
                </span>
              </span>
              <span className="font-medium tabular-nums text-slate-900">
                {formatNumber(tp.price, 2)}
              </span>
            </li>
          );
        })}
      </ul>

      <dl className="mt-2">
        <Row
          label={L.volume}
          value={
            volume == null ? L.dash : `${formatNumber(volume, 2)} ${L.lot}`
          }
        />
      </dl>

      <PriceRelationshipBar analysis={analysis} />
    </section>
  );
};

const Row = ({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) => (
  <div className="flex items-baseline justify-between gap-3">
    <dt className="text-xs text-slate-500">{label}</dt>
    <dd
      className={cn(
        "tabular-nums text-slate-900",
        emphasize ? "font-semibold" : "font-medium",
      )}
    >
      {value}
    </dd>
  </div>
);
