"use client";

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

  const scaleMin =
    snap.support != null && snap.resistance != null
      ? Math.min(snap.support.low, snap.current ?? snap.support.low)
      : null;
  const scaleMax =
    snap.support != null && snap.resistance != null
      ? Math.max(snap.resistance.high, snap.current ?? snap.resistance.high)
      : null;
  const span =
    scaleMin != null && scaleMax != null && scaleMax > scaleMin
      ? scaleMax - scaleMin
      : null;

  const pct = (price: number) =>
    span == null || scaleMin == null
      ? 50
      : Math.max(0, Math.min(100, ((price - scaleMin) / span) * 100));

  const insight =
    signal === "SHORT" && hasEntryZone
      ? L.keyLevelsInsightSell
      : signal === "LONG" && hasEntryZone
        ? L.keyLevelsInsightBuy
        : snap.priceBetween
          ? L.keyLevelsInsightBetween
          : null;

  const rail = span != null &&
    snap.support != null &&
    snap.resistance != null &&
    snap.current != null;

  const entryBlock = (
    <div
      className={cn(
        "rounded-[var(--radius-tab)] border border-[var(--border)] px-3 py-2.5",
        signal === "SHORT" && "border-[var(--negative)]/25",
        signal === "LONG" && "border-[var(--positive)]/25",
      )}
    >
      <p className="text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        {L.entryZone}
      </p>
      {hasEntryZone ? (
        <>
          <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground)]">
            {fmt(Math.min(setup!.entryZoneLow!, setup!.entryZoneHigh!))} –{" "}
            {fmt(Math.max(setup!.entryZoneLow!, setup!.entryZoneHigh!))}
          </p>
          {signal === "SHORT" ? (
            <ol className="mt-2 space-y-0.5 text-[12px] text-[var(--foreground-secondary)]">
              <li>{L.keyLevelsFlowSell1}</li>
              <li>{L.keyLevelsFlowSell2}</li>
              <li>{L.keyLevelsFlowSell3}</li>
              <li>{L.keyLevelsFlowSell4}</li>
            </ol>
          ) : signal === "LONG" ? (
            <ol className="mt-2 space-y-0.5 text-[12px] text-[var(--foreground-secondary)]">
              <li>{L.keyLevelsFlowBuy1}</li>
              <li>{L.keyLevelsFlowBuy2}</li>
              <li>{L.keyLevelsFlowBuy3}</li>
              <li>{L.keyLevelsFlowBuy4}</li>
            </ol>
          ) : null}
        </>
      ) : (
        <p className="mt-1 text-[14px] text-[var(--muted)]">{L.noEntryZone}</p>
      )}
      {insight ? (
        <p className="mt-2 rounded-[var(--radius-tab)] bg-[var(--accent-subtle)] px-2.5 py-2 text-[12px] leading-snug text-[var(--foreground-secondary)]">
          {insight}
        </p>
      ) : null}
    </div>
  );

  return (
    <section className="border-t border-[var(--border)] pt-4" aria-label={L.keyLevelsTitle}>
      <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        {L.keyLevelsTitle}
      </p>
      <p className="mt-0.5 text-[12px] text-[var(--muted)]">{L.keyLevelsDisclaimer}</p>

      <div
        className={cn(
          "mt-3 gap-4",
          unified ? "grid grid-cols-1 lg:grid-cols-12" : "grid grid-cols-1",
        )}
      >
        <div className={cn(unified ? "lg:col-span-8" : "")}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="rounded-[var(--radius-tab)] bg-[var(--positive-subtle)] px-3 py-2.5">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--positive)] uppercase">
                {L.keyLevelsSupport}
              </p>
              <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground)]">
                {snap.support
                  ? formatLevelRange(snap.support, fmt)
                  : L.noSupportNearby}
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--foreground-secondary)]">
                {snap.support ? _levelMeta(snap.support) : L.dash}
              </p>
            </div>

            <div className="rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-3 py-2.5 text-center sm:text-left">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                {L.keyLevelsCurrent}
              </p>
              <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground)]">
                {snap.current == null ? L.dash : fmt(snap.current)}
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--accent)]" aria-hidden>
                ●
              </p>
            </div>

            <div className="rounded-[var(--radius-tab)] bg-[var(--negative-subtle)] px-3 py-2.5 sm:text-right">
              <p className="text-[11px] font-semibold tracking-wide text-[var(--negative)] uppercase">
                {L.keyLevelsResistance}
              </p>
              <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground)]">
                {snap.resistance
                  ? formatLevelRange(snap.resistance, fmt)
                  : L.noResistanceNearby}
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--foreground-secondary)]">
                {snap.resistance ? _levelMeta(snap.resistance) : L.dash}
              </p>
            </div>
          </div>

          {rail ? (
            <div className="mt-4 hidden sm:block" aria-hidden>
              <div className="relative h-3">
                <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-[var(--border)]" />
                <div
                  className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full bg-[var(--positive)]/35"
                  style={{
                    left: `${pct(snap.support!.low)}%`,
                    width: `${Math.max(2, pct(snap.support!.high) - pct(snap.support!.low))}%`,
                  }}
                />
                <div
                  className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full bg-[var(--negative)]/35"
                  style={{
                    left: `${pct(snap.resistance!.low)}%`,
                    width: `${Math.max(2, pct(snap.resistance!.high) - pct(snap.resistance!.low))}%`,
                  }}
                />
                <div
                  className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--accent)] bg-[var(--surface)]"
                  style={{ left: `${pct(snap.current!)}%` }}
                />
              </div>
              <div className="mt-2 flex justify-between gap-2 text-[11px] tabular-nums text-[var(--muted)]">
                <span className="text-[var(--positive)]">
                  {formatNumber(snap.support!.distancePts, 1)} pts (
                  {formatNumber(snap.support!.distancePct, 2)}%)
                </span>
                <span className="text-[var(--negative)]">
                  {formatNumber(snap.resistance!.distancePts, 1)} pts (
                  {formatNumber(snap.resistance!.distancePct, 2)}%)
                </span>
              </div>
            </div>
          ) : null}

          {/* Mobile simplified distances */}
          {rail ? (
            <div className="mt-3 space-y-1 text-[12px] sm:hidden">
              <p className="text-[var(--positive)]">
                → {L.keyLevelsSupport}: {formatNumber(snap.support!.distancePts, 1)}{" "}
                pts
              </p>
              <p className="text-[var(--negative)]">
                → {L.keyLevelsResistance}:{" "}
                {formatNumber(snap.resistance!.distancePts, 1)} pts
              </p>
            </div>
          ) : null}
        </div>

        <div className={cn(unified ? "lg:col-span-4" : "mt-3")}>{entryBlock}</div>
      </div>
    </section>
  );
};
