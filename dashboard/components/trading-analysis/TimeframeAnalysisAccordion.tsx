"use client";

import { useState } from "react";
import type { MultiTimeframeAnalysis } from "@/domain";
import { formatNumber } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";

type TimeframeRow = MultiTimeframeAnalysis["timeframes"][string];

type TimeframeAnalysisAccordionProps = {
  timeframe: string;
  row: TimeframeRow;
};

const formatOrDash = (value: number | null | undefined, digits = 2): string => {
  if (value == null || Number.isNaN(value)) return L.dash;
  return formatNumber(value, digits);
};

export const TimeframeAnalysisAccordion = ({
  timeframe,
  row,
}: TimeframeAnalysisAccordionProps) => {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-slate-100 first:border-t-0">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 py-2.5 text-left text-sm"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`tf-details-${timeframe}`}
      >
        <span className="font-semibold text-slate-800">{timeframe}</span>
        <span className="text-xs text-slate-500">{open ? "▲" : "▼"}</span>
      </button>
      {open ? (
        <dl
          id={`tf-details-${timeframe}`}
          className="grid grid-cols-2 gap-x-3 gap-y-1.5 pb-3 text-xs sm:grid-cols-3"
        >
          <Item label="Close" value={formatOrDash(row.close)} />
          <Item label="EMA20" value={formatOrDash(row.ema20)} />
          <Item label="EMA50" value={formatOrDash(row.ema50)} />
          <Item label="EMA200" value={formatOrDash(row.ema200)} />
          <Item label="RSI14" value={formatOrDash(row.rsi14)} />
          <Item label="ATR14" value={formatOrDash(row.atr14)} />
          <Item label="MACD" value={formatOrDash(row.macd, 4)} />
          <Item label="MACD Signal" value={formatOrDash(row.macdSignal, 4)} />
          <Item label="MACD Histogram" value={formatOrDash(row.macdHistogram, 4)} />
          <Item label="Structure" value={row.structureClassification || L.dash} />
          <Item label="Support" value={formatOrDash(row.nearestSupport)} />
          <Item label="Resistance" value={formatOrDash(row.nearestResistance)} />
          <Item
            label="Trend score"
            value={formatOrDash(row.score?.trendScore)}
          />
          <Item
            label="Structure score"
            value={formatOrDash(row.score?.structureScore)}
          />
          <Item
            label="Momentum score"
            value={formatOrDash(row.score?.momentumScore)}
          />
          <Item
            label="Location score"
            value={formatOrDash(row.score?.locationScore)}
          />
          <Item
            label="Volume score"
            value={formatOrDash(row.score?.volumeScore)}
          />
        </dl>
      ) : null}
    </div>
  );
};

const Item = ({ label, value }: { label: string; value: string }) => (
  <div>
    <dt className="text-slate-500">{label}</dt>
    <dd className="font-medium tabular-nums text-slate-800">{value}</dd>
  </div>
);
