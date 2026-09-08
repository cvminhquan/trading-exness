"use client";

import type { MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type PriceRelationshipBarProps = {
  analysis: MultiTimeframeAnalysis;
};

/**
 * Horizontal relationship: TP1 — Current — Entry zone — SL (presentation only).
 * Uses backend setup prices; no new trading logic.
 */
export const PriceRelationshipBar = ({ analysis }: PriceRelationshipBarProps) => {
  const setup = analysis.setup;
  if (!setup || setup.state === "NO_SETUP") return null;

  const current = analysis.currentPrice;
  const tp1 = setup.takeProfits.find((t) => t.level === 1)?.price ?? null;
  const sl = setup.stopLoss ?? null;
  const zoneLow = setup.entryZoneLow ?? null;
  const zoneHigh = setup.entryZoneHigh ?? null;
  const zoneMid =
    zoneLow != null && zoneHigh != null ? (zoneLow + zoneHigh) / 2 : null;

  const points = [
    { key: "TP1", value: tp1 },
    { key: "CURRENT", value: current },
    { key: "ENTRY", value: zoneMid },
    { key: "SL", value: sl },
  ].filter((p): p is { key: string; value: number } => p.value != null);

  if (points.length < 2) return null;

  const vals = points.map((p) => p.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;

  const pct = (v: number) => ((v - min) / span) * 100;

  const inZone =
    setup.state === "ENTRY_ZONE" ||
    (current != null &&
      zoneLow != null &&
      zoneHigh != null &&
      current >= Math.min(zoneLow, zoneHigh) &&
      current <= Math.max(zoneLow, zoneHigh));

  const distance = setup.distanceToEntry;

  return (
    <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-2" aria-label="Price relationship">
      <div className="relative h-8">
        <div className="absolute top-1/2 left-0 right-0 h-px -translate-y-1/2 bg-slate-200" />
        {zoneLow != null && zoneHigh != null ? (
          <div
            className="absolute top-1/2 h-1.5 -translate-y-1/2 bg-slate-200"
            style={{
              left: `${Math.min(pct(zoneLow), pct(zoneHigh))}%`,
              width: `${Math.abs(pct(zoneHigh) - pct(zoneLow))}%`,
            }}
            title={`${L.entryZoneLabel}: ${formatNumber(zoneLow, 2)} – ${formatNumber(zoneHigh, 2)}`}
          />
        ) : null}
        {points.map((p) => (
          <div
            key={p.key}
            className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
            style={{ left: `${pct(p.value)}%` }}
          >
            <span
              className={cn(
                "size-1.5 rounded-full",
                p.key === "CURRENT" ? "bg-slate-900" : "bg-slate-400",
              )}
            />
            <span className="mt-1 text-[9px] font-medium uppercase tracking-wide text-slate-500">
              {p.key}
            </span>
          </div>
        ))}
      </div>
      <p className={cn("text-[11px]", inZone ? "text-slate-700" : "text-slate-600")}>
        {inZone
          ? L.priceInEntryZone
          : L.priceAwayFromEntry.replace(
              "{n}",
              distance == null ? L.dash : formatNumber(Math.abs(distance), 2),
            )}
      </p>
    </div>
  );
};
