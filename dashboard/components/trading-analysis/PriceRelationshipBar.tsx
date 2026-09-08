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
 */
export const PriceRelationshipBar = ({ analysis }: PriceRelationshipBarProps) => {
  const setup = analysis.setup;
  if (!setup || setup.state === "NO_SETUP") return null;

  const current = analysis.currentPrice;
  const tp1 = setup.takeProfits.find((t) => t.level === 1)?.price ?? null;
  const sl = setup.stopLoss ?? null;
  const zoneLow = setup.entryZoneLow ?? null;
  const zoneHigh = setup.entryZoneHigh ?? null;

  const anchors = [
    { key: "TP1", value: tp1, emphasize: false },
    { key: "CURRENT", value: current, emphasize: true },
    { key: "SL", value: sl, emphasize: false },
  ].filter((p): p is { key: string; value: number; emphasize: boolean } => p.value != null);

  if (anchors.length < 2 && zoneLow == null) return null;

  const allVals = [
    ...anchors.map((a) => a.value),
    ...(zoneLow != null ? [zoneLow] : []),
    ...(zoneHigh != null ? [zoneHigh] : []),
  ];
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
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

  const labelOffset = (key: string) =>
    key === "CURRENT" ? "top-6" : key === "TP1" ? "top-0" : "top-6";

  return (
    <div className="mt-5 space-y-2" aria-label="Price relationship">
      <div className="relative h-[4.5rem]">
        <div className="absolute top-3.5 right-0 left-0 h-[2px] bg-[var(--border-strong)]" />
        {zoneLow != null && zoneHigh != null ? (
          <div
            className="absolute top-2.5 h-4 rounded-[var(--radius-control)] bg-[var(--accent-muted)]/70"
            style={{
              left: `${Math.min(pct(zoneLow), pct(zoneHigh))}%`,
              width: `${Math.max(Math.abs(pct(zoneHigh) - pct(zoneLow)), 2)}%`,
            }}
            title={`${L.entryZoneLabel}: ${formatNumber(zoneLow, 2)} – ${formatNumber(zoneHigh, 2)}`}
          />
        ) : null}
        {anchors.map((p) => (
          <div
            key={p.key}
            className={cn(
              "absolute flex -translate-x-1/2 flex-col items-center",
              labelOffset(p.key),
            )}
            style={{ left: `${pct(p.value)}%` }}
          >
            <span
              className={cn(
                "rounded-full border-2 border-[var(--surface)]",
                p.emphasize
                  ? "size-3.5 bg-[var(--foreground)]"
                  : "size-2.5 bg-[var(--muted)]",
              )}
            />
            <span
              className={cn(
                "mt-1 font-semibold tracking-wide uppercase",
                p.emphasize
                  ? "text-[12px] text-[var(--foreground)]"
                  : "text-[12px] text-[var(--muted)]",
              )}
            >
              {p.key}
            </span>
            <span
              className={cn(
                "tabular-nums",
                p.emphasize
                  ? "text-[13px] font-bold text-[var(--foreground)]"
                  : "text-[12px] font-medium text-[var(--foreground-secondary)]",
              )}
            >
              {formatNumber(p.value, 2)}
            </span>
          </div>
        ))}
        {zoneLow != null && zoneHigh != null ? (
          <p
            className="absolute -top-0.5 text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase"
            style={{
              left: `${(Math.min(pct(zoneLow), pct(zoneHigh)) + Math.max(pct(zoneLow), pct(zoneHigh))) / 2}%`,
              transform: "translateX(-50%)",
            }}
          >
            ENTRY ZONE
          </p>
        ) : null}
      </div>
      <p className="text-[13px] font-medium text-[var(--foreground-secondary)]">
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
