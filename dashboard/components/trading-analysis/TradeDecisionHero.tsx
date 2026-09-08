"use client";

import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import {
  computeDisplayWeightedScore,
  formatCandleClock,
  formatRelativeAgo,
  freshnessTone,
  hasDirectionalSetup,
  TF_ORDER,
} from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type TradeDecisionHeroProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

const ROLE: Record<string, string> = {
  M15: "PRIMARY",
  H1: "CONFIRMATION",
  H4: "CONTEXT",
  D1: "MACRO",
};

/**
 * Workstation decision panel — terminal scan, not marketing hero.
 */
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

  const decisionTitle =
    signal === "WAIT"
      ? L.waitHeadline
      : signal === "LONG"
        ? "BUY / LONG"
        : "SELL / SHORT";

  const setupLabel =
    signal === "WAIT"
      ? L.waitMessage
      : hasSetup
        ? setupState.replaceAll("_", " ")
        : L.noSetupMessage;

  const statusLabel = isBlocked
    ? L.blocked
    : isReady
      ? L.ready
      : freshnessTone(freshness) === "warn"
        ? freshness
        : null;

  return (
    <section
      className="border-b border-slate-200 pb-4"
      aria-label={L.sectionTitle}
    >
      {/* Row 1: symbol · price · freshness */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-base font-semibold tracking-tight text-slate-900">
            {analysis.symbol}
          </h2>
          <p className="text-base font-semibold tabular-nums text-slate-900">
            {analysis.currentPrice == null
              ? L.dash
              : formatNumber(analysis.currentPrice, 2)}
          </p>
          <span
            className={cn(
              "text-[10px] font-semibold uppercase tracking-wide",
              freshness === "LIVE" && "text-emerald-800",
              freshnessTone(freshness) === "warn" && "text-amber-800",
              freshnessTone(freshness) === "bad" && "text-rose-800",
              freshnessTone(freshness) === "neutral" &&
                freshness !== "LIVE" &&
                "text-slate-500",
            )}
            title={`${L.lastM15Candle}: ${formatCandleClock(m15?.candleTimestamp)} · ${L.lastQuote}: ${formatRelativeAgo(analysis.generatedAt)}`}
          >
            {freshness}
          </span>
        </div>
        <p className="text-[10px] text-slate-400">
          {L.lastM15Candle} {formatCandleClock(m15?.candleTimestamp)}
        </p>
      </div>

      {/* Row 2: decision · MTF score */}
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p
            className={cn(
              "text-2xl font-semibold tracking-tight",
              signal === "LONG" && "text-emerald-800",
              signal === "SHORT" && "text-rose-800",
              signal === "WAIT" && "text-slate-800",
            )}
          >
            {decisionTitle}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">{setupLabel}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">
            MTF
          </p>
          <p
            className={cn(
              "text-xl font-semibold tabular-nums",
              (score ?? 0) > 0 && "text-emerald-800",
              (score ?? 0) < 0 && "text-rose-800",
              (score ?? 0) === 0 && "text-slate-800",
            )}
          >
            {score == null ? L.dash : formatNumber(score, 2)}
          </p>
        </div>
      </div>

      {/* TF roles — M15 emphasized */}
      <dl className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
        {TF_ORDER.map((tf) => {
          const row = analysis.timeframes[tf];
          if (!row) return null;
          const tfScore = row.score?.totalScore;
          const isPrimary = tf === "M15";
          return (
            <div
              key={tf}
              className={cn(
                "flex items-baseline justify-between gap-2 py-0.5",
                isPrimary && "sm:col-span-1",
              )}
            >
              <dt
                className={cn(
                  "text-[11px] text-slate-500",
                  isPrimary && "font-semibold text-slate-700",
                )}
              >
                {tf}{" "}
                <span className="font-normal text-slate-400">{ROLE[tf]}</span>
              </dt>
              <dd
                className={cn(
                  "tabular-nums",
                  isPrimary ? "text-sm font-semibold" : "text-sm font-medium",
                  (tfScore ?? 0) > 0 && "text-emerald-800",
                  (tfScore ?? 0) < 0 && "text-rose-800",
                  (tfScore ?? 0) === 0 && "text-slate-700",
                )}
              >
                {tfScore == null ? L.dash : formatNumber(tfScore, 2)}
              </dd>
            </div>
          );
        })}
      </dl>

      {/* Status strip */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2">
        <p className="text-xs text-slate-600">{setupState.replaceAll("_", " ")}</p>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          <span
            className="text-slate-500"
            title={L.confidenceTooltip}
          >
            {L.evidenceAlignment}{" "}
            <span className="font-semibold tabular-nums text-slate-800">
              {formatNumber(analysis.confidenceScore, 1)}%
            </span>
          </span>
          {statusLabel ? (
            <span
              className={cn(
                "font-semibold uppercase tracking-wide",
                isBlocked && "text-rose-800",
                isReady && !isBlocked && "text-emerald-800",
                !isBlocked && !isReady && "text-amber-800",
              )}
            >
              {statusLabel}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
};
