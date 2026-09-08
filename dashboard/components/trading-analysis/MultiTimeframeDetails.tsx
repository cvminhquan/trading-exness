"use client";

import { useState } from "react";
import { TimeframeAnalysisAccordion } from "@/components/trading-analysis/TimeframeAnalysisAccordion";
import type { MultiTimeframeAnalysis } from "@/domain";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { TF_ORDER } from "@/lib/trading-analysis/mtf-display";

type MultiTimeframeDetailsProps = {
  analysis: MultiTimeframeAnalysis;
};

/** Tertiary — collapsible indicator detail (scores already in decision panel). */
export const MultiTimeframeDetails = ({ analysis }: MultiTimeframeDetailsProps) => {
  const [open, setOpen] = useState(false);

  return (
    <section className="border-t border-slate-200 pt-3" aria-label={L.mtfDetailsTitle}>
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {L.mtfDetailsTitle}
        </h3>
        <span className="text-[11px] text-slate-400">
          {open ? "Thu gọn" : "Chi tiết chỉ báo"}
        </span>
      </button>

      {open ? (
        <div className="mt-1">
          {TF_ORDER.map((tf) => {
            const row = analysis.timeframes[tf];
            if (!row) return null;
            return (
              <TimeframeAnalysisAccordion key={tf} timeframe={tf} row={row} />
            );
          })}
        </div>
      ) : null}
    </section>
  );
};
