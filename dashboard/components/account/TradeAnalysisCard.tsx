"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { TradeAnalysis } from "@/domain";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import { TRADE_ANALYSIS, UI } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type TradeAnalysisCardProps = {
  analysis: TradeAnalysis;
};

const dash = TRADE_ANALYSIS.dash;

const formatOrDash = (value: number | null | undefined, digits = 2): string => {
  if (value == null || Number.isNaN(value)) return dash;
  return formatNumber(value, digits);
};

export const TradeAnalysisCard = ({ analysis }: TradeAnalysisCardProps) => {
  const isWait = analysis.signal === "WAIT";
  const trade = analysis.trade;
  const sizing = analysis.sizing;

  return (
    <Card aria-label={TRADE_ANALYSIS.title}>
      <CardContent className="space-y-4 p-4">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {TRADE_ANALYSIS.title}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-slate-900">
              {analysis.symbol}{" "}
              <span className="font-normal text-slate-500">{analysis.timeframe}</span>
            </p>
            <p className="text-[11px] text-slate-500">{TRADE_ANALYSIS.subtitle}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <StatusChip
              label={analysis.status}
              tone={
                analysis.status === "LIVE"
                  ? "neutral"
                  : analysis.status === "STALE"
                    ? "warn"
                    : "bad"
              }
            />
            <StatusChip
              label={analysis.signal}
              tone={
                analysis.signal === "BUY"
                  ? "good"
                  : analysis.signal === "SELL"
                    ? "bad"
                    : "neutral"
              }
            />
          </div>
        </header>

        <section aria-label={TRADE_ANALYSIS.signal} className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {TRADE_ANALYSIS.signal}
          </p>
          <p
            className={cn(
              "text-2xl font-bold tracking-tight",
              analysis.signal === "BUY" && "text-emerald-700",
              analysis.signal === "SELL" && "text-rose-700",
              analysis.signal === "WAIT" && "text-slate-700",
            )}
          >
            {analysis.strategySignal ?? analysis.signal}
          </p>
          {analysis.contextAssessment ? (
            <p className="text-xs text-slate-600">
              {TRADE_ANALYSIS.contextAssessment}:{" "}
              <span className="font-semibold">{analysis.contextAssessment}</span>
            </p>
          ) : null}
        </section>

        {analysis.structure ? (
          <section aria-label={TRADE_ANALYSIS.marketStructure} className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {TRADE_ANALYSIS.marketStructure}
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric
                label={TRADE_ANALYSIS.structureLabel}
                value={analysis.structure.classification}
              />
              <Metric
                label={TRADE_ANALYSIS.latestSwing}
                value={
                  analysis.structure.sequence.length > 0
                    ? analysis.structure.sequence.join(" → ")
                    : dash
                }
              />
              <Metric
                label={TRADE_ANALYSIS.support}
                value={formatOrDash(analysis.structure.nearestSupport, 2)}
              />
              <Metric
                label={TRADE_ANALYSIS.resistance}
                value={formatOrDash(analysis.structure.nearestResistance, 2)}
              />
              <Metric
                label={TRADE_ANALYSIS.entry}
                value={isWait || !trade ? dash : formatOrDash(trade.entry, 3)}
              />
              <Metric
                label={TRADE_ANALYSIS.distanceToResistance}
                value={
                  analysis.structure.distanceToResistance == null
                    ? dash
                    : `${formatOrDash(analysis.structure.distanceToResistance, 2)} · ${formatOrDash(analysis.structure.distanceToResistanceAtr, 2)} ${TRADE_ANALYSIS.atrUnit}`
                }
              />
              <Metric
                label={TRADE_ANALYSIS.distanceToSupport}
                value={
                  analysis.structure.distanceToSupport == null
                    ? dash
                    : `${formatOrDash(analysis.structure.distanceToSupport, 2)} · ${formatOrDash(analysis.structure.distanceToSupportAtr, 2)} ${TRADE_ANALYSIS.atrUnit}`
                }
              />
            </div>
          </section>
        ) : null}

        <section aria-label={TRADE_ANALYSIS.market} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Metric label={UI.bid} value={formatOrDash(analysis.market.bid, 3)} />
          <Metric label={UI.ask} value={formatOrDash(analysis.market.ask, 3)} />
          <Metric
            label={UI.spread}
            value={formatOrDash(analysis.market.spreadPoints, 1)}
          />
          <Metric label={TRADE_ANALYSIS.regime} value={analysis.regime} />
        </section>

        <section aria-label={TRADE_ANALYSIS.tradePlan} className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {TRADE_ANALYSIS.tradePlan}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              label={TRADE_ANALYSIS.entry}
              value={isWait || !trade ? dash : formatOrDash(trade.entry, 3)}
            />
            <Metric
              label={TRADE_ANALYSIS.stopLoss}
              value={isWait || !trade ? dash : formatOrDash(trade.stopLoss, 3)}
            />
            <Metric
              label={TRADE_ANALYSIS.takeProfit}
              value={isWait || !trade ? dash : formatOrDash(trade.takeProfit, 3)}
            />
            <Metric
              label={TRADE_ANALYSIS.riskReward}
              value={
                isWait || !trade ? dash : formatOrDash(trade.riskRewardRatio, 2)
              }
            />
          </div>
        </section>

        <section aria-label={TRADE_ANALYSIS.positionSize} className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {TRADE_ANALYSIS.positionSize}
          </p>
          {sizing ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric
                label={TRADE_ANALYSIS.equity}
                value={formatCurrency(sizing.equity)}
              />
              <Metric
                label={TRADE_ANALYSIS.riskPercent}
                value={formatPercent(sizing.riskPercent)}
              />
              <Metric
                label={TRADE_ANALYSIS.riskBudget}
                value={formatCurrency(sizing.riskBudgetUsd)}
              />
              <Metric
                label={TRADE_ANALYSIS.rawLot}
                value={formatOrDash(sizing.rawVolume, 3)}
              />
              <Metric
                label={TRADE_ANALYSIS.calculatedLot}
                value={isWait ? dash : formatOrDash(sizing.normalizedVolume, 3)}
              />
              <Metric
                label={TRADE_ANALYSIS.brokerMinimum}
                value={formatOrDash(sizing.brokerMinVolume, 3)}
              />
              <Metric
                label={TRADE_ANALYSIS.estimatedRisk}
                value={
                  sizing.estimatedRiskUsd == null
                    ? dash
                    : `${formatCurrency(sizing.estimatedRiskUsd)} (${formatOrDash(sizing.estimatedRiskPct, 2)}%)`
                }
              />
              <Metric
                label={TRADE_ANALYSIS.brokerExecutable}
                value={sizing.brokerExecutable ? TRADE_ANALYSIS.yes : TRADE_ANALYSIS.no}
              />
              <Metric
                label={TRADE_ANALYSIS.riskAcceptable}
                value={sizing.riskAcceptable ? TRADE_ANALYSIS.yes : TRADE_ANALYSIS.no}
              />
            </div>
          ) : (
            <p className="text-sm text-slate-500">{dash}</p>
          )}
        </section>

        <section aria-label={TRADE_ANALYSIS.executionAssessment} className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {TRADE_ANALYSIS.executionAssessment}
          </p>
          <StatusChip
            label={analysis.executionStatus}
            tone={
              analysis.executionStatus === "READY"
                ? "good"
                : analysis.executionStatus === "BLOCKED"
                  ? "warn"
                  : "neutral"
            }
            large
          />
          <p className="text-[11px] text-slate-500">{TRADE_ANALYSIS.researchOnly}</p>
        </section>

        <ReasonsList title={TRADE_ANALYSIS.why} reasons={analysis.reasons} />
        {analysis.blockingReasons.length > 0 ? (
          <ReasonsList
            title={TRADE_ANALYSIS.blocking}
            reasons={analysis.blockingReasons}
            forceFail
          />
        ) : null}
      </CardContent>
    </Card>
  );
};

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-md bg-slate-50 px-2.5 py-2">
    <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
      {label}
    </p>
    <p className="mt-0.5 text-sm font-semibold text-slate-900">{value}</p>
  </div>
);

const StatusChip = ({
  label,
  tone,
  large,
}: {
  label: string;
  tone: "good" | "bad" | "warn" | "neutral";
  large?: boolean;
}) => (
  <span
    className={cn(
      "inline-flex items-center rounded-full px-2 py-0.5 font-semibold",
      large ? "text-sm px-3 py-1" : "text-[11px]",
      tone === "good" && "bg-emerald-50 text-emerald-700",
      tone === "bad" && "bg-rose-50 text-rose-700",
      tone === "warn" && "bg-amber-50 text-amber-800",
      tone === "neutral" && "bg-slate-100 text-slate-700",
    )}
  >
    {label}
  </span>
);

const ReasonsList = ({
  title,
  reasons,
  forceFail,
}: {
  title: string;
  reasons: TradeAnalysis["reasons"];
  forceFail?: boolean;
}) => (
  <section aria-label={title} className="space-y-1.5">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {title}
    </p>
    <ul className="space-y-1">
      {reasons.map((item) => {
        const ok = forceFail ? false : item.passed;
        return (
          <li
            key={`${item.code}-${item.message}`}
            className={cn(
              "flex gap-2 text-xs",
              ok ? "text-emerald-800" : "text-rose-800",
            )}
          >
            <span aria-hidden="true">{ok ? "✓" : "✕"}</span>
            <span>
              <span className="font-medium">{item.code}</span>
              {": "}
              {item.message}
            </span>
          </li>
        );
      })}
    </ul>
  </section>
);
