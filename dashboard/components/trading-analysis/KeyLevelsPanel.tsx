"use client";

import { Lightbulb } from "lucide-react";
import type { MultiTimeframeAnalysis } from "@/domain";
import { formatMarketPrice, formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import {
  buildKeyLevelsSnapshot,
  formatLevelRange,
  type KeyLevelView,
} from "@/lib/trading-analysis/key-levels";
import { cn } from "@/lib/utils";

type KeyLevelsPanelProps = {
  analysis: MultiTimeframeAnalysis;
  currentPrice?: number | null;
  digits?: number;
  /** Side-by-side entry column on wide layouts. */
  unified?: boolean;
};

const _levelMeta = (level: KeyLevelView): string => {
  if (level.timeframe) return level.timeframe;
  return L.dash;
};

/** Ba mốc tick đều — tránh nhãn chồng. */
const _axisTicks = (min: number, max: number): [number, number, number] => [
  min,
  min + (max - min) / 2,
  max,
];

export const KeyLevelsPanel = ({
  analysis,
  currentPrice,
  digits = 2,
  unified = false,
}: KeyLevelsPanelProps) => {
  const snap = buildKeyLevelsSnapshot(analysis, currentPrice);
  const fmt = (n: number) => formatMarketPrice(n, Math.min(digits, 2));
  const setup = analysis.setup;
  const hasEntryZone =
    setup != null &&
    setup.state !== "NO_SETUP" &&
    setup.entryZoneLow != null &&
    setup.entryZoneHigh != null;
  const signal = analysis.finalSignal;

  const pad =
    snap.support != null && snap.resistance != null
      ? Math.max(
          (snap.resistance.high - snap.support.low) * 0.18,
          Math.abs(snap.current ?? snap.support.low) * 0.002,
          8,
        )
      : 0;
  const scaleMin =
    snap.support != null && snap.resistance != null
      ? Math.min(snap.support.low, snap.current ?? snap.support.low) - pad
      : null;
  const scaleMax =
    snap.support != null && snap.resistance != null
      ? Math.max(snap.resistance.high, snap.current ?? snap.resistance.high) +
        pad
      : null;
  const span =
    scaleMin != null && scaleMax != null && scaleMax > scaleMin
      ? scaleMax - scaleMin
      : null;

  const pct = (price: number) =>
    span == null || scaleMin == null
      ? 50
      : Math.max(0, Math.min(100, ((price - scaleMin) / span) * 100));

  /** Segment trên trục 0–100; min width được căn giữa (không lệch sang phải). */
  const zoneSeg = (low: number, high: number, minWidthPct = 2.5) => {
    const a = pct(Math.min(low, high));
    const b = pct(Math.max(low, high));
    const mid = (a + b) / 2;
    let width = Math.max(b - a, minWidthPct);
    let left = mid - width / 2;
    if (left < 0) {
      width = Math.min(width, 100);
      left = 0;
    }
    if (left + width > 100) {
      left = Math.max(0, 100 - width);
    }
    return { left, width, mid };
  };

  const insight =
    signal === "SHORT" && hasEntryZone
      ? L.keyLevelsInsightSell
      : signal === "LONG" && hasEntryZone
        ? L.keyLevelsInsightBuy
        : snap.priceBetween
          ? L.keyLevelsInsightBetween
          : null;

  const rail =
    span != null &&
    snap.support != null &&
    snap.resistance != null &&
    snap.current != null;

  const ticks =
    scaleMin != null && scaleMax != null ? _axisTicks(scaleMin, scaleMax) : null;
  const currentLeft = snap.current != null ? pct(snap.current) : 50;
  const supportSeg =
    snap.support != null
      ? zoneSeg(snap.support.low, snap.support.high)
      : null;
  const resistanceSeg =
    snap.resistance != null
      ? zoneSeg(snap.resistance.low, snap.resistance.high)
      : null;

  const insideSupport =
    snap.support != null &&
    snap.current != null &&
    snap.current >= snap.support.low &&
    snap.current <= snap.support.high;
  const insideResistance =
    snap.resistance != null &&
    snap.current != null &&
    snap.current >= snap.resistance.low &&
    snap.current <= snap.resistance.high;

  return (
    <section
      className="border-t border-[var(--border)] pt-5"
      aria-label={L.keyLevelsTitle}
    >
      <div
        className={cn(
          "gap-3",
          unified ? "grid grid-cols-1 lg:grid-cols-12" : "grid grid-cols-1",
        )}
      >
        {/* ── KEY LEVELS card ── */}
        <div
          className={cn(
            "rounded-[var(--radius-tab)] border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-[var(--shadow-xs)] md:px-5",
            unified ? "lg:col-span-8" : "",
          )}
        >
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h3 className="text-[16px] font-bold tracking-[0.04em] text-[var(--foreground)] uppercase md:text-[17px]">
              {L.keyLevelsTitle}
            </h3>
            <span
              className="inline-flex size-4 shrink-0 items-center justify-center rounded-full border border-[var(--border-strong)] text-[10px] font-bold text-[var(--muted)]"
              title={L.keyLevelsDisclaimer}
              aria-label={L.keyLevelsDisclaimer}
            >
              i
            </span>
            <p className="text-[12px] leading-snug text-[var(--muted)]">
              {L.keyLevelsDisclaimer}
            </p>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
            <div className="rounded-[var(--radius-control)] bg-[var(--positive-subtle)] px-3 py-3">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--positive)] uppercase">
                {L.keyLevelsSupport}
              </p>
              <p className="mt-1.5 text-[16px] font-bold tabular-nums tracking-tight text-[var(--positive)] md:text-[17px]">
                {snap.support
                  ? formatLevelRange(snap.support, fmt)
                  : L.noSupportNearby}
              </p>
              <p className="mt-1 text-[12px] text-[var(--muted)]">
                {snap.support ? _levelMeta(snap.support) : L.dash}
              </p>
            </div>

            <div className="px-1 py-3 text-center sm:px-2">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                {L.keyLevelsCurrent}
              </p>
              <p className="mt-1.5 text-[16px] font-bold tabular-nums tracking-tight text-[var(--foreground)] md:text-[17px]">
                {snap.current == null ? L.dash : fmt(snap.current)}
              </p>
              {rail ? (
                <p
                  className="mt-1 text-[10px] font-semibold text-[var(--accent)]"
                  aria-hidden
                >
                  ▼
                </p>
              ) : null}
            </div>

            <div className="rounded-[var(--radius-control)] bg-[var(--negative-subtle)] px-3 py-3 sm:text-right">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--negative)] uppercase">
                {L.keyLevelsResistance}
              </p>
              <p className="mt-1.5 text-[16px] font-bold tabular-nums tracking-tight text-[var(--negative)] md:text-[17px]">
                {snap.resistance
                  ? formatLevelRange(snap.resistance, fmt)
                  : L.noResistanceNearby}
              </p>
              <p className="mt-1 text-[12px] text-[var(--muted)]">
                {snap.resistance ? _levelMeta(snap.resistance) : L.dash}
              </p>
            </div>
          </div>

          {rail && ticks && supportSeg && resistanceSeg ? (
            <div className="mt-4 hidden sm:block" aria-hidden>
              {/* Cùng hệ tọa độ %: zone / marker / tick */}
              <div className="relative h-8 w-full">
                <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-[var(--border)]" />

                <div
                  className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-[var(--positive)]/45"
                  style={{
                    left: `${supportSeg.left}%`,
                    width: `${supportSeg.width}%`,
                  }}
                />
                <div
                  className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-[var(--negative)]/45"
                  style={{
                    left: `${resistanceSeg.left}%`,
                    width: `${resistanceSeg.width}%`,
                  }}
                />

                <div
                  className="absolute top-1/2 z-10 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] shadow-[0_0_0_3px_var(--surface),0_0_0_5px_var(--accent)]"
                  style={{ left: `${currentLeft}%` }}
                  title={fmt(snap.current!)}
                />
              </div>

              <div className="relative mt-2 h-4 overflow-visible">
                {ticks.map((t, i) => (
                  <span
                    key={t}
                    className={cn(
                      "absolute text-[10px] tabular-nums text-[var(--muted)]",
                      i === 0 && "left-0 translate-x-0",
                      i === 1 && "left-1/2 -translate-x-1/2",
                      i === 2 && "right-0 left-auto translate-x-0",
                    )}
                  >
                    {fmt(t)}
                  </span>
                ))}
              </div>
              
              <div className="mt-1.5 flex items-start justify-between gap-4 text-[11px] font-semibold tabular-nums">
                <p className="max-w-[48%] text-left leading-snug text-[var(--positive)]">
                  {insideSupport
                    ? `● trong hỗ trợ · ${formatNumber(snap.support!.distancePts, 1)} pts`
                    : `← ${formatNumber(snap.support!.distancePts, 1)} pts (${formatNumber(snap.support!.distancePct, 2)}%)`}
                </p>
                <p className="max-w-[48%] text-right leading-snug text-[var(--negative)]">
                  {insideResistance
                    ? `${formatNumber(snap.resistance!.distancePts, 1)} pts · trong kháng cự ●`
                    : `${formatNumber(snap.resistance!.distancePts, 1)} pts (${formatNumber(snap.resistance!.distancePct, 2)}%) →`}
                </p>
              </div>

              
            </div>
          ) : null}

          {rail ? (
            <div className="mt-3 space-y-1 text-[12px] font-medium sm:hidden">
              <p className="text-[var(--positive)]">
                {L.keyLevelsSupport}:{" "}
                {formatNumber(snap.support!.distancePts, 1)} pts (
                {formatNumber(snap.support!.distancePct, 2)}%)
              </p>
              <p className="text-[var(--negative)]">
                {L.keyLevelsResistance}:{" "}
                {formatNumber(snap.resistance!.distancePts, 1)} pts (
                {formatNumber(snap.resistance!.distancePct, 2)}%)
              </p>
            </div>
          ) : null}
        </div>

        {/* ── ENTRY ZONE card ── */}
        <div
          className={cn(
            "flex flex-col rounded-[var(--radius-tab)] border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-[var(--shadow-xs)] md:px-5",
            unified ? "lg:col-span-4" : "",
          )}
        >
          <h3 className="text-[16px] font-bold tracking-[0.04em] text-[var(--foreground)] uppercase md:text-[17px]">
            {L.entryZone}
          </h3>

          {hasEntryZone ? (
            <p className="mt-3 text-[18px] font-bold tabular-nums tracking-tight text-[var(--foreground)] md:text-[20px]">
              {fmt(Math.min(setup!.entryZoneLow!, setup!.entryZoneHigh!))} –{" "}
              {fmt(Math.max(setup!.entryZoneLow!, setup!.entryZoneHigh!))}
            </p>
          ) : (
            <p className="mt-3 text-[14px] text-[var(--muted)]">{L.noEntryZone}</p>
          )}

          {signal === "SHORT" && hasEntryZone ? (
            <ol className="mt-3 space-y-1.5 text-[13px] text-[var(--foreground-secondary)]">
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↓
                </span>
                {L.keyLevelsFlowSell1}
              </li>
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↓
                </span>
                {L.keyLevelsFlowSell2}
              </li>
              <li className="flex items-center gap-2 font-medium text-[var(--accent)]">
                <span className="w-3 text-center" aria-hidden>
                  ●
                </span>
                {L.keyLevelsFlowCurrent}
              </li>
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↓
                </span>
                {L.keyLevelsFlowSell4}
              </li>
            </ol>
          ) : null}

          {signal === "LONG" && hasEntryZone ? (
            <ol className="mt-3 space-y-1.5 text-[13px] text-[var(--foreground-secondary)]">
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↑
                </span>
                {L.keyLevelsFlowBuy1}
              </li>
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↑
                </span>
                {L.keyLevelsFlowBuy2}
              </li>
              <li className="flex items-center gap-2 font-medium text-[var(--accent)]">
                <span className="w-3 text-center" aria-hidden>
                  ●
                </span>
                {L.keyLevelsFlowCurrent}
              </li>
              <li className="flex items-center gap-2">
                <span className="w-3 text-center text-[var(--muted)]" aria-hidden>
                  ↑
                </span>
                {L.keyLevelsFlowBuy4}
              </li>
            </ol>
          ) : null}

          {insight ? (
            <div className="mt-4 flex gap-2.5 rounded-[var(--radius-control)] bg-[var(--accent-subtle)] px-3 py-2.5">
              <Lightbulb
                className="mt-0.5 size-4 shrink-0 text-[var(--accent)]"
                aria-hidden
              />
              <p className="text-[12px] leading-snug font-medium text-[var(--foreground-secondary)]">
                {insight}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
};
