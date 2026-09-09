"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { useWatchlistQuotes } from "@/hooks/use-watchlist-quotes";
import { formatCurrency, formatNumber } from "@/lib/format";
import { MULTI_TIMEFRAME_ANALYSIS as L } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type MultiTimeframeAnalysisCardProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

const formatOrDash = (value: number | null | undefined, digits = 2): string => {
  if (value == null || Number.isNaN(value)) return L.dash;
  return formatNumber(value, digits);
};

const TF_ORDER = ["M15", "H1", "H4", "D1"] as const;

export const MultiTimeframeAnalysisCard = ({
  analysis,
  eligibility,
}: MultiTimeframeAnalysisCardProps) => {
  const { displayPriceOf } = useWatchlistQuotes();
  const displayPrice = displayPriceOf(analysis.symbol, analysis.currentPrice);
  const setup = analysis.setup;
  const sizing = analysis.sizing;
  const primary = analysis.timeframes.M15 ?? Object.values(analysis.timeframes)[0];
  const setupState = eligibility?.setupState ?? setup?.state ?? "NO_SETUP";
  const isEligible = eligibility?.eligible === true;

  return (
    <Card aria-label={L.title}>
      <CardContent className="space-y-4 p-4">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {L.title}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-slate-900">
              {analysis.symbol}{" "}
              <span className="font-normal text-slate-500">MULTI-TIMEFRAME</span>
            </p>
            <p className="text-[11px] text-slate-500">{L.subtitle}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <StatusChip
              label={analysis.freshness}
              tone={analysis.freshness === "LIVE" ? "neutral" : "warn"}
            />
            <StatusChip
              label={analysis.finalSignal}
              tone={
                analysis.finalSignal === "LONG"
                  ? "good"
                  : analysis.finalSignal === "SHORT"
                    ? "bad"
                    : "neutral"
              }
            />
          </div>
        </header>

        <section aria-label={L.timeframes} className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {L.timeframes}
          </p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {TF_ORDER.map((tf) => {
              const row = analysis.timeframes[tf];
              if (!row) return null;
              return (
                <div
                  key={tf}
                  className="flex items-center justify-between rounded-md border border-slate-200 px-2.5 py-1.5 text-sm"
                >
                  <span className="font-medium text-slate-700">{tf}</span>
                  <span
                    className={cn(
                      "font-semibold",
                      row.signal === "LONG" && "text-emerald-700",
                      row.signal === "SHORT" && "text-rose-700",
                      row.signal === "NEUTRAL" && "text-slate-600",
                    )}
                  >
                    {row.signal}{" "}
                    <span className="font-normal text-slate-500">
                      {formatNumber(row.confidence, 0)}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section aria-label={L.finalSignal} className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {L.finalSignal}
          </p>
          <p
            className={cn(
              "text-2xl font-bold tracking-tight",
              analysis.finalSignal === "LONG" && "text-emerald-700",
              analysis.finalSignal === "SHORT" && "text-rose-700",
              analysis.finalSignal === "WAIT" && "text-slate-700",
            )}
          >
            {analysis.finalSignal}
          </p>
          <p
            className="text-xs text-slate-600"
            title={L.confidenceTooltip}
            aria-label={L.confidenceTooltip}
          >
            {L.confidence}:{" "}
            <span className="font-semibold">
              {formatNumber(analysis.confidenceScore, 0)}/100
            </span>{" "}
            <span className="text-slate-400">({analysis.confidenceMeaning})</span>
          </p>
        </section>

        {setup ? (
          <section aria-label={L.setup} className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {L.setup}
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric label={L.setupType} value={setup.type} />
              <Metric label={L.setupState} value={setupState} />
              <Metric
                label={L.currentPrice}
                value={formatOrDash(displayPrice, 2)}
              />
              <Metric label={L.entry} value={formatOrDash(setup.entryPrice, 2)} />
              <Metric
                label={L.entryZone}
                value={
                  setup.entryZoneLow != null && setup.entryZoneHigh != null
                    ? `${formatOrDash(setup.entryZoneLow, 2)} – ${formatOrDash(setup.entryZoneHigh, 2)}`
                    : L.dash
                }
              />
              <Metric label={L.stopLoss} value={formatOrDash(setup.stopLoss, 2)} />
            </div>
            {setup.takeProfits.length > 0 ? (
              <ul className="space-y-1 text-sm text-slate-700">
                {setup.takeProfits.map((tp) => (
                  <li key={tp.level}>
                    TP{tp.level}: {formatOrDash(tp.price, 2)} · {formatNumber(tp.allocationPct, 0)}%
                    · R:R {formatNumber(tp.rr, 2)}
                  </li>
                ))}
              </ul>
            ) : null}
            {setup.state === "WAITING_FOR_ENTRY" ||
            setupState === "WAITING_FOR_ENTRY" ? (
              <p className="text-xs font-medium text-amber-700">{L.waitingForEntry}</p>
            ) : null}
          </section>
        ) : null}

        {eligibility ? (
          <section aria-label={L.executionEligibility} className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {L.executionEligibility}
            </p>
            <p
              className={cn(
                "text-lg font-bold",
                isEligible ? "text-emerald-700" : "text-rose-700",
              )}
            >
              {isEligible ? L.eligible : L.blocked}
            </p>
            {eligibility.reasons.length > 0 ? (
              <ul className="space-y-1 text-sm text-slate-700" aria-label={L.eligibilityReasons}>
                {eligibility.reasons.map((code) => (
                  <li key={code}>• {code}</li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}

        <section aria-label={L.technical} className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {L.technical}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric label={L.trend} value={analysis.trend} />
            <Metric label={L.structure} value={analysis.structureSummary || L.dash} />
            <Metric
              label={L.support}
              value={
                analysis.keySupports.length > 0
                  ? analysis.keySupports.map((v) => formatOrDash(v, 2)).join(", ")
                  : L.dash
              }
            />
            <Metric
              label={L.resistance}
              value={
                analysis.keyResistances.length > 0
                  ? analysis.keyResistances.map((v) => formatOrDash(v, 2)).join(", ")
                  : L.dash
              }
            />
            {primary ? (
              <>
                <Metric
                  label="EMA"
                  value={`${formatOrDash(primary.ema20)} / ${formatOrDash(primary.ema50)} / ${formatOrDash(primary.ema200)}`}
                />
                <Metric label="RSI" value={formatOrDash(primary.rsi14, 1)} />
                <Metric
                  label="MACD"
                  value={`${formatOrDash(primary.macd, 3)} / ${formatOrDash(primary.macdSignal, 3)}`}
                />
                <Metric label="ATR" value={formatOrDash(primary.atr14, 2)} />
                <Metric
                  label={L.volume}
                  value={`${primary.volume.state} (${formatOrDash(primary.volume.ratio, 2)})`}
                />
                <Metric label={L.pattern} value={primary.pattern.type} />
              </>
            ) : null}
          </div>
        </section>

        {sizing ? (
          <section aria-label={L.sizing} className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {L.sizing}
            </p>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Metric label={L.equity} value={formatCurrency(sizing.equity)} />
              <Metric
                label="Risk %"
                value={`${formatNumber(sizing.riskPercent, 2)}%`}
              />
              <Metric
                label={L.brokerExecutable}
                value={sizing.brokerExecutable ? L.yes : L.no}
              />
              <Metric
                label={L.riskAcceptable}
                value={sizing.riskAcceptable ? L.yes : L.no}
              />
            </div>
            <p className="text-xs text-slate-600">
              {L.executionAssessment}:{" "}
              <span className="font-semibold">{analysis.executionAssessment}</span>
            </p>
          </section>
        ) : null}

        {analysis.summaryVi.length > 0 ? (
          <section aria-label={L.why} className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {L.why}
            </p>
            <ul className="list-disc space-y-1 pl-4 text-sm text-slate-700">
              {analysis.summaryVi.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {analysis.warnings.length > 0 ? (
          <section aria-label={L.warnings} className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
              {L.warnings}
            </p>
            <ul className="space-y-1 text-sm text-amber-800">
              {analysis.warnings.map((w) => (
                <li key={`${w.code}-${w.message}`}>! {w.code}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <p className="text-[11px] text-slate-500">{L.researchOnly}</p>
      </CardContent>
    </Card>
  );
};

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0">
    <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
    <p className="truncate text-sm font-medium text-slate-800">{value}</p>
  </div>
);

const StatusChip = ({
  label,
  tone,
}: {
  label: string;
  tone: "good" | "bad" | "warn" | "neutral";
}) => (
  <span
    className={cn(
      "rounded px-2 py-0.5 text-[11px] font-semibold",
      tone === "good" && "bg-emerald-50 text-emerald-800",
      tone === "bad" && "bg-rose-50 text-rose-800",
      tone === "warn" && "bg-amber-50 text-amber-800",
      tone === "neutral" && "bg-slate-100 text-slate-700",
    )}
  >
    {label}
  </span>
);
