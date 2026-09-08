"use client";

import type { MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type PriceRelationshipBarProps = {
  analysis: MultiTimeframeAnalysis;
};

/**
 * Tóm tắt thứ tự quan hệ giá — không lặp lại số đã hiện ở trên.
 */
export const PriceRelationshipBar = ({ analysis }: PriceRelationshipBarProps) => {
  const setup = analysis.setup;
  if (!setup || setup.state === "NO_SETUP") return null;

  const current = analysis.currentPrice;
  const tp1 = setup.takeProfits.find((t) => t.level === 1)?.price ?? null;
  const sl = setup.stopLoss ?? null;
  const zoneLow = setup.entryZoneLow ?? null;
  const zoneHigh = setup.entryZoneHigh ?? null;

  const points: { key: string; value: number }[] = [];
  if (tp1 != null) points.push({ key: "TP1", value: tp1 });
  if (current != null) points.push({ key: "CURRENT", value: current });
  if (zoneLow != null && zoneHigh != null) {
    points.push({ key: "ENTRY", value: (zoneLow + zoneHigh) / 2 });
  }
  if (sl != null) points.push({ key: "SL", value: sl });

  if (points.length < 2) return null;

  const order = [...points].sort((a, b) => a.value - b.value);

  const inZone =
    setup.state === "ENTRY_ZONE" ||
    (current != null &&
      zoneLow != null &&
      zoneHigh != null &&
      current >= Math.min(zoneLow, zoneHigh) &&
      current <= Math.max(zoneLow, zoneHigh));

  const distance = setup.distanceToEntry;

  return (
    <div
      className="mt-4 border-t border-[var(--border)] pt-4"
      aria-label="Price relationship"
    >
      <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        Thứ tự giá
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] font-semibold">
        {order.map((p, i) => (
          <span key={p.key} className="inline-flex items-center gap-1.5">
            {i > 0 ? (
              <span className="text-[var(--muted)]" aria-hidden>
                →
              </span>
            ) : null}
            <span
              className={cn(
                "rounded-full px-2 py-0.5 tracking-wide uppercase",
                p.key === "CURRENT"
                  ? "bg-[var(--foreground)] text-[var(--surface)]"
                  : p.key === "ENTRY"
                    ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                    : "bg-[var(--surface-subtle)] text-[var(--foreground-secondary)]",
              )}
            >
              {p.key}
            </span>
          </span>
        ))}
      </div>
      <p className="mt-3 text-[13px] font-medium text-[var(--foreground-secondary)]">
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
