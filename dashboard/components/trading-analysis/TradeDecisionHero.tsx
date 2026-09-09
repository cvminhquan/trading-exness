"use client";

import { MarketMove } from "@/components/market/MarketMove";
import { MtfScoreBar } from "@/components/trading-analysis/MtfScoreBar";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { useSessionQuoteMoves } from "@/hooks/use-session-quote-moves";
import { useWatchlistQuotes } from "@/hooks/use-watchlist-quotes";
import { formatMarketPrice, formatScore } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import {
  DASHBOARD_SYMBOL_LABELS,
  type DashboardSymbol,
  isDashboardSymbol,
} from "@/lib/symbols/config";
import {
  computeDisplayWeightedScore,
  formatCandleClock,
  formatRelativeAgo,
  freshnessTone,
  hasDirectionalSetup,
  structureBiasLabel,
} from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type TradeDecisionHeroProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

export const TradeDecisionHero = ({
  analysis,
  eligibility,
}: TradeDecisionHeroProps) => {
  const score = computeDisplayWeightedScore(analysis);
  const setupState =
    eligibility?.setupState ?? analysis.setup?.state ?? "NO_SETUP";
  const hasSetup = hasDirectionalSetup(analysis);
  const isBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && eligibility.eligible === false && hasSetup);
  const isReady =
    eligibility?.eligible === true || analysis.executionAssessment === "READY";
  const signal = analysis.finalSignal;
  const m15 = analysis.timeframes.M15;
  const freshness = analysis.freshness;

  const { quotes, quoteOf, displayPriceOf } = useWatchlistQuotes();
  const moves = useSessionQuoteMoves(quotes);
  const move = moves[analysis.symbol]?.move ?? null;
  const quote = quoteOf(analysis.symbol);
  const digits = quote?.digits ?? 2;
  const displayPrice = displayPriceOf(analysis.symbol, analysis.currentPrice);

  const decisionTitle =
    signal === "WAIT"
      ? L.waitHeadline
      : signal === "LONG"
        ? "BUY / LONG"
        : "SELL / SHORT";

  const setupHuman =
    signal === "WAIT"
      ? L.waitMessage
      : setupState === "WAITING_FOR_ENTRY"
        ? L.waitingForEntry
        : setupState === "ENTRY_ZONE"
          ? L.entryZoneState
          : setupState.replaceAll("_", " ");

  const statusLabel = isReady
    ? L.ready
    : freshnessTone(freshness) === "warn"
      ? freshness
      : null;

  const m15Bias = structureBiasLabel(m15?.structureClassification, {
    bullish: L.structureBullish,
    bearish: L.structureBearish,
    mixed: L.structureMixed,
  });

  const m15Score = m15?.score?.totalScore ?? null;
  const m15Tone =
    m15Score == null
      ? "neutral"
      : m15Score > 0
        ? "bull"
        : m15Score < 0
          ? "bear"
          : "neutral";

  const pairLabel = isDashboardSymbol(analysis.symbol)
    ? DASHBOARD_SYMBOL_LABELS[analysis.symbol as DashboardSymbol]
    : null;

  return (
    <section
      className="surface-card flex h-full min-h-0 flex-col px-5 py-5"
      aria-label={L.sectionTitle}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-[22px] font-semibold tracking-tight text-[var(--foreground)]">
              {analysis.symbol}
            </h2>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-bold uppercase tracking-wide",
                freshness === "LIVE" &&
                  "bg-[var(--positive-subtle)] text-[var(--positive)]",
                freshnessTone(freshness) === "warn" &&
                  "bg-[var(--warning-subtle)] text-[var(--warning)]",
                freshnessTone(freshness) === "bad" &&
                  "bg-[var(--negative-subtle)] text-[var(--negative)]",
              )}
              title={`${L.lastM15Candle}: ${formatCandleClock(m15?.candleTimestamp)} · ${L.lastQuote}: ${formatRelativeAgo(analysis.generatedAt)}`}
            >
              <span className="size-1.5 rounded-full bg-current" aria-hidden />
              {freshness}
            </span>
          </div>
          {pairLabel ? (
            <p className="mt-0.5 text-[13px] text-[var(--muted)]">{pairLabel}</p>
          ) : null}
        </div>
        <p className="text-[12px] text-[var(--muted)]">
          {L.lastM15Candle} {formatCandleClock(m15?.candleTimestamp)}
        </p>
      </div>

      <p className="mt-3 text-[34px] leading-none font-semibold tabular-nums tracking-tight text-[var(--foreground)]">
        {displayPrice == null
          ? L.dash
          : `$${formatMarketPrice(displayPrice, Math.min(digits, 2))}`}
      </p>
      {move ? (
        <MarketMove
          className="mt-2 text-[14px] font-semibold"
          abs={move.abs}
          pct={move.pct}
          absAsPrice
          priceDigits={Math.min(digits, 2)}
        />
      ) : null}

      <div className="mt-5 flex flex-wrap items-stretch gap-3">
        <div
          className={cn(
            "min-w-[12rem] flex-1 rounded-[var(--radius-tab)] px-4 py-3",
            signal === "LONG" && "bg-[var(--positive-subtle)]",
            signal === "SHORT" && "bg-[var(--negative-subtle)]",
            signal === "WAIT" && "bg-[var(--surface-subtle)]",
          )}
        >
          <p
            className={cn(
              "text-[28px] leading-tight font-semibold tracking-tight",
              signal === "LONG" && "text-[var(--positive)]",
              signal === "SHORT" && "text-[var(--negative)]",
              signal === "WAIT" && "text-[var(--foreground)]",
            )}
          >
            {decisionTitle}
          </p>
          <p className="mt-1 text-[14px] text-[var(--foreground-secondary)]">
            {setupHuman}
          </p>
          {statusLabel ? (
            <p
              className={cn(
                "mt-1 text-[13px] font-semibold uppercase tracking-wide",
                isBlocked && "text-[var(--negative)]",
                isReady && !isBlocked && "text-[var(--positive)]",
                !isBlocked && !isReady && "text-[var(--warning)]",
              )}
            >
              {statusLabel}
            </p>
          ) : null}
        </div>

        <div className="min-w-[8rem] rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-4 py-3 text-right">
          <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
            MTF SCORE
          </p>
          <p
            className={cn(
              "mt-1 text-[28px] leading-none font-semibold tabular-nums",
              (score ?? 0) > 0 && "text-[var(--positive)]",
              (score ?? 0) < 0 && "text-[var(--negative)]",
              (score ?? 0) === 0 && "text-[var(--foreground)]",
            )}
          >
            {score == null ? L.dash : formatScore(score, 2)}
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-5">
        <div
          className={cn(
            "rounded-[var(--radius-tab)] border border-[var(--border)] px-3 py-3 md:col-span-2 xl:col-span-2",
            m15Tone === "bear" &&
              "border-l-[3px] border-l-[var(--negative)] bg-[var(--negative-subtle)]",
            m15Tone === "bull" &&
              "border-l-[3px] border-l-[var(--positive)] bg-[var(--positive-subtle)]",
            m15Tone === "neutral" && "bg-[var(--surface-subtle)]",
          )}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-[12px] font-semibold tracking-wide text-[var(--foreground-secondary)] uppercase">
              M15 PRIMARY
            </p>
            <p
              className={cn(
                "text-[12px] font-semibold tracking-wide uppercase",
                m15Tone === "bear" && "text-[var(--negative)]",
                m15Tone === "bull" && "text-[var(--positive)]",
                m15Tone === "neutral" && "text-[var(--muted)]",
              )}
            >
              {m15Bias}
            </p>
          </div>
          <p
            className={cn(
              "mt-1 text-[26px] leading-none font-semibold tabular-nums",
              m15Tone === "bear" && "text-[var(--negative)]",
              m15Tone === "bull" && "text-[var(--positive)]",
              m15Tone === "neutral" && "text-[var(--foreground)]",
            )}
          >
            {m15Score == null ? L.dash : formatScore(m15Score, 2)}
          </p>
          <div className="mt-2.5">
            <MtfScoreBar score={m15Score} />
          </div>
        </div>

        {(["H1", "H4", "D1"] as const).map((tf) => {
          const row = analysis.timeframes[tf];
          const tfScore = row?.score?.totalScore;
          const role =
            tf === "H1" ? "CONFIRMATION" : tf === "H4" ? "CONTEXT" : "MACRO";
          const bias = structureBiasLabel(row?.structureClassification, {
            bullish: L.structureBullish,
            bearish: L.structureBearish,
            mixed: L.structureMixed,
          });
          const stronger = tf === "H1";
          return (
            <div
              key={tf}
              className={cn(
                "rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-3 py-3",
                stronger && "ring-1 ring-[var(--border)]",
              )}
            >
              <p className="text-[12px] font-semibold text-[var(--foreground)]">
                {tf}{" "}
                <span className="font-medium text-[var(--muted)]">{role}</span>
              </p>
              <p
                className={cn(
                  "mt-1 font-semibold tabular-nums",
                  stronger ? "text-[20px]" : "text-[18px]",
                  (tfScore ?? 0) > 0 && "text-[var(--positive)]",
                  (tfScore ?? 0) < 0 && "text-[var(--negative)]",
                  (tfScore ?? 0) === 0 && "text-[var(--foreground-secondary)]",
                )}
              >
                {tfScore == null ? L.dash : formatScore(tfScore, 2)}
              </p>
              <p className="mt-1 text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
                {bias}
              </p>
            </div>
          );
        })}
      </div>

      <div className="mt-4" title={L.confidenceTooltip}>
        <div className="mb-1.5 flex items-center justify-between gap-2 text-[13px]">
          <span className="text-[var(--muted)]">{L.evidenceAlignment}</span>
          <span className="font-semibold tabular-nums text-[var(--foreground-secondary)]">
            {formatScore(analysis.confidenceScore, 1)}%
          </span>
        </div>
        <div className="relative h-2 overflow-hidden rounded-full bg-[var(--surface-subtle)]">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent)]"
            style={{
              width: `${Math.max(0, Math.min(100, analysis.confidenceScore))}%`,
            }}
          />
        </div>
      </div>
    </section>
  );
};
