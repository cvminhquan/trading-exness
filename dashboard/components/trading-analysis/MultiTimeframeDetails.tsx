"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { TimeframeAnalysisAccordion } from "@/components/trading-analysis/TimeframeAnalysisAccordion";
import type { MultiTimeframeAnalysis } from "@/domain";
import { formatScore } from "@/lib/format";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import {
  TF_ORDER,
  structureBiasLabel,
} from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type MultiTimeframeDetailsProps = {
  analysis: MultiTimeframeAnalysis;
};

export const MultiTimeframeDetails = ({ analysis }: MultiTimeframeDetailsProps) => {
  const [open, setOpen] = useState(false);

  return (
    <section className="surface-card px-5 py-3" aria-label={L.mtfDetailsTitle}>
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 rounded-[var(--radius-control)] py-1 text-left transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <h3 className="text-[16px] font-semibold text-[var(--foreground)]">
          {L.mtfDetailsTitle}
        </h3>
        <span className="flex items-center gap-1 text-[13px] font-medium text-[var(--muted)]">
          {open ? "Thu gọn" : "Chi tiết chỉ báo"}
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </span>
      </button>

      {!open ? (
        <ul className="mt-2 divide-y divide-[var(--border)]">
          {TF_ORDER.map((tf) => {
            const row = analysis.timeframes[tf];
            if (!row) return null;
            const score = row.score?.totalScore;
            const bias = structureBiasLabel(row.structureClassification, {
              bullish: L.structureBullish,
              bearish: L.structureBearish,
              mixed: L.structureMixed,
            });
            return (
              <li
                key={tf}
                className="flex h-11 items-center justify-between gap-3 text-[14px]"
              >
                <span className="font-semibold text-[var(--foreground)]">{tf}</span>
                <span className="flex items-center gap-3 tabular-nums">
                  <span
                    className={cn(
                      "font-semibold",
                      (score ?? 0) > 0 && "text-[var(--positive)]",
                      (score ?? 0) < 0 && "text-[var(--negative)]",
                      (score ?? 0) === 0 && "text-[var(--foreground-secondary)]",
                    )}
                  >
                    {score == null ? L.dash : formatScore(score, 2)}
                  </span>
                  <span className="w-16 text-right text-[12px] text-[var(--muted)] uppercase">
                    {bias}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="mt-2">
          {TF_ORDER.map((tf) => {
            const row = analysis.timeframes[tf];
            if (!row) return null;
            return (
              <TimeframeAnalysisAccordion key={tf} timeframe={tf} row={row} />
            );
          })}
        </div>
      )}
    </section>
  );
};
