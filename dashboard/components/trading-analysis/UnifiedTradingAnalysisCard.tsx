"use client";

import { useId, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronUp } from "lucide-react";
import { MarketMove } from "@/components/market/MarketMove";
import { DecisionReasonsCard } from "@/components/trading-analysis/DecisionReasonsCard";
import { KeyLevelsPanel } from "@/components/trading-analysis/KeyLevelsPanel";
import { MtfScoreBar } from "@/components/trading-analysis/MtfScoreBar";
import { RiskChecksSection } from "@/components/trading-analysis/RiskChecksSection";
import { TradePlanSection } from "@/components/trading-analysis/TradePlanSection";
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

type UnifiedTradingAnalysisCardProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

const TF_CARDS = [
  { tf: "M15" as const, role: L.rolePrimary, subtitle: "Xu hướng ngắn hạn", primary: true },
  { tf: "H1" as const, role: L.roleConfirmation, subtitle: "Tín hiệu xác nhận" },
  { tf: "H4" as const, role: L.roleContext, subtitle: "Bối cảnh trung hạn" },
  { tf: "D1" as const, role: L.roleMacro, subtitle: "Xu hướng dài hạn" },
];

/**
 * One full-width analysis workflow card — presentation only.
 * No broker mutation controls.
 */
export const UnifiedTradingAnalysisCard = ({
  analysis,
  eligibility,
}: UnifiedTradingAnalysisCardProps) => {
  const detailsId = useId();
  const [detailsOpen, setDetailsOpen] = useState(true);
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

  const pairLabel = isDashboardSymbol(analysis.symbol)
    ? DASHBOARD_SYMBOL_LABELS[analysis.symbol as DashboardSymbol]
    : null;

  const handleToggleDetails = () => {
    setDetailsOpen((v) => !v);
  };

  return (
    <section
      className="surface-card px-5 py-5 md:px-6 md:py-6"
      aria-label={L.unifiedCardTitle}
    >
      {/* ── Header / market state (always visible) ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-[20px] font-semibold tracking-tight text-[var(--foreground)] md:text-[22px]">
              {analysis.symbol}
            </h2>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide",
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
          <p className="mt-0.5 text-[13px] text-[var(--muted)]">
            {pairLabel ? `${pairLabel} · ` : null}
            {L.lastM15Candle} {formatCandleClock(m15?.candleTimestamp)}
          </p>
        </div>

        <button
          type="button"
          onClick={handleToggleDetails}
          aria-expanded={detailsOpen}
          aria-controls={detailsId}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-[13px] font-semibold text-[var(--foreground-secondary)] transition-colors hover:border-[var(--accent-muted)] hover:text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          aria-label={detailsOpen ? L.collapseDetails : L.expandDetails}
        >
          {detailsOpen ? (
            <ChevronUp className="size-4" aria-hidden />
          ) : (
            <ChevronDown className="size-4" aria-hidden />
          )}
          {detailsOpen ? L.collapseDetails : L.expandDetails}
        </button>
      </div>

      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-[36px] leading-none font-semibold tabular-nums tracking-tight text-[var(--foreground)] md:text-[40px]">
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
        </div>

        <div className="flex min-w-0 flex-1 flex-wrap items-stretch gap-3 lg:max-w-xl lg:justify-end">
          <div
            className={cn(
              "min-w-[11rem] flex-1 rounded-[var(--radius-tab)] px-4 py-3",
              signal === "LONG" && "bg-[var(--positive-subtle)]",
              signal === "SHORT" && "bg-[var(--negative-subtle)]",
              signal === "WAIT" && "bg-[var(--surface-subtle)]",
            )}
          >
            <div className="flex items-start gap-2">
              {signal === "SHORT" ? (
                <ArrowDown
                  className="mt-1 size-6 shrink-0 text-[var(--negative)]"
                  aria-hidden
                />
              ) : null}
              {signal === "LONG" ? (
                <ArrowUp
                  className="mt-1 size-6 shrink-0 text-[var(--positive)]"
                  aria-hidden
                />
              ) : null}
              <div className="min-w-0">
                <p
                  className={cn(
                    "text-[24px] leading-tight font-semibold tracking-tight md:text-[26px]",
                    signal === "LONG" && "text-[var(--positive)]",
                    signal === "SHORT" && "text-[var(--negative)]",
                    signal === "WAIT" && "text-[var(--foreground)]",
                  )}
                >
                  {decisionTitle}
                </p>
                <p className="mt-1 text-[13px] text-[var(--foreground-secondary)]">
                  {setupHuman}
                </p>
                {isReady ? (
                  <span className="mt-2 inline-flex rounded-full bg-[var(--positive-subtle)] px-2 py-0.5 text-[11px] font-bold tracking-wide text-[var(--positive)] uppercase">
                    {L.ready}
                  </span>
                ) : null}
                {isBlocked && !isReady ? (
                  <span className="mt-2 inline-flex rounded-full bg-[var(--negative-subtle)] px-2 py-0.5 text-[11px] font-bold tracking-wide text-[var(--negative)] uppercase">
                    {L.blocked}
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <div
            className="min-w-[7.5rem] rounded-[var(--radius-tab)] bg-[var(--surface-subtle)] px-4 py-3 text-right"
            title={L.structureScoreTooltip}
          >
            <p className="text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
              {L.mtfScore}
            </p>
            <p
              className={cn(
                "mt-1 text-[24px] leading-none font-semibold tabular-nums md:text-[26px]",
                (score ?? 0) > 0 && "text-[var(--positive)]",
                (score ?? 0) < 0 && "text-[var(--negative)]",
                (score ?? 0) === 0 && "text-[var(--foreground)]",
              )}
            >
              {score == null ? L.dash : formatScore(score, 2)}
            </p>
          </div>
        </div>
      </div>

      {!detailsOpen ? (
        <p className="mt-4 text-[13px] text-[var(--muted)]" role="status">
          {L.detailsCollapsedHint}
        </p>
      ) : null}

      <div
        id={detailsId}
        hidden={!detailsOpen}
        className={cn(!detailsOpen && "hidden")}
      >
        {/* ── Key levels + entry ── */}
        <div className="mt-2">
          <KeyLevelsPanel
            analysis={analysis}
            currentPrice={displayPrice}
            digits={digits}
            unified
          />
        </div>

        {/* ── Trade plan | Risk ── */}
        <div className="mt-5 grid grid-cols-1 gap-6 border-t border-[var(--border)] pt-5 md:grid-cols-2">
          <div className="min-w-0 rounded-[var(--radius-tab)] bg-[var(--surface-subtle)]/60 px-4 py-3.5">
            <TradePlanSection analysis={analysis} />
          </div>
          <div className="min-w-0 rounded-[var(--radius-tab)] bg-[var(--surface-subtle)]/60 px-4 py-3.5">
            <RiskChecksSection analysis={analysis} eligibility={eligibility} />
          </div>
        </div>

        {/* ── MTF ── */}
        <div className="mt-5 border-t border-[var(--border)] pt-5">
          <p className="text-[12px] font-semibold tracking-wide text-[var(--muted)] uppercase">
            {L.mtfSectionTitle}
          </p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {TF_CARDS.map(({ tf, role, subtitle, primary }) => {
              const row = analysis.timeframes[tf];
              const tfScore = row?.score?.totalScore ?? null;
              const unavailable = row == null || row.status === "INSUFFICIENT";
              const bias = structureBiasLabel(row?.structureClassification, {
                bullish: L.structureBullish,
                bearish: L.structureBearish,
                mixed: L.structureMixed,
              });
              const biasTone =
                bias === L.structureBullish
                  ? "bull"
                  : bias === L.structureBearish
                    ? "bear"
                    : "neutral";
              const scoreTone =
                tfScore == null
                  ? "neutral"
                  : tfScore > 0
                    ? "bull"
                    : tfScore < 0
                      ? "bear"
                      : "neutral";

              return (
                <div
                  key={tf}
                  className={cn(
                    "rounded-[var(--radius-tab)] border border-[var(--border)] px-3 py-3",
                    primary &&
                      biasTone === "bear" &&
                      "border-l-[3px] border-l-[var(--negative)] bg-[var(--negative-subtle)]",
                    primary &&
                      biasTone === "bull" &&
                      "border-l-[3px] border-l-[var(--positive)] bg-[var(--positive-subtle)]",
                    !primary && "bg-[var(--surface-subtle)]",
                  )}
                  title={L.structureScoreTooltip}
                >
                  <p className="text-[11px] font-semibold tracking-wide text-[var(--foreground-secondary)] uppercase">
                    {tf}{" "}
                    <span className="font-medium text-[var(--muted)]">{role}</span>
                  </p>
                  {unavailable ? (
                    <p className="mt-2 text-[13px] text-[var(--muted)]">
                      {L.tfUnavailable}
                    </p>
                  ) : (
                    <>
                      <p
                        className={cn(
                          "mt-1.5 text-[17px] leading-none font-bold tracking-wide uppercase",
                          biasTone === "bear" && "text-[var(--negative)]",
                          biasTone === "bull" && "text-[var(--positive)]",
                          biasTone === "neutral" &&
                            "text-[var(--foreground-secondary)]",
                        )}
                      >
                        {bias}
                      </p>
                      <p
                        className={cn(
                          "mt-2 text-[14px] font-semibold tabular-nums",
                          scoreTone === "bear" && "text-[var(--negative)]",
                          scoreTone === "bull" && "text-[var(--positive)]",
                          scoreTone === "neutral" && "text-[var(--muted)]",
                        )}
                      >
                        {tfScore == null ? L.dash : formatScore(tfScore, 2)}
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--muted)]">
                        {subtitle}
                      </p>
                      {primary ? (
                        <div className="mt-2.5">
                          <MtfScoreBar score={tfScore} />
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Evidence alignment ── */}
        <div className="mt-5" title={L.confidenceTooltip}>
          <div className="mb-1.5 flex items-center justify-between gap-2 text-[13px]">
            <span className="inline-flex items-center gap-1.5 text-[var(--muted)]">
              {L.evidenceAlignment}
              <span
                className="inline-flex size-3.5 items-center justify-center rounded-full border border-[var(--border)] text-[9px] font-bold text-[var(--muted)]"
                aria-label={L.confidenceTooltip}
                title={L.confidenceTooltip}
              >
                i
              </span>
            </span>
            <span className="font-semibold tabular-nums text-[var(--foreground-secondary)]">
              {formatScore(analysis.confidenceScore, 1)}%
            </span>
          </div>
          <div
            className="relative h-2 overflow-hidden rounded-full bg-[var(--surface-subtle)]"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.max(0, Math.min(100, analysis.confidenceScore))}
            aria-label={L.confidenceTooltip}
          >
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent)]"
              style={{
                width: `${Math.max(0, Math.min(100, analysis.confidenceScore))}%`,
              }}
            />
          </div>
        </div>

        {/* ── Decision reasons ── */}
        <div className="mt-5 border-t border-[var(--border)] pt-4">
          <DecisionReasonsCard
            analysis={analysis}
            eligibility={eligibility}
            embedded
          />
        </div>
      </div>
    </section>
  );
};
