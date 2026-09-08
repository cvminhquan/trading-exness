"use client";

import { useState } from "react";
import type { ExecutionCandidateStatus, MultiTimeframeAnalysis } from "@/domain";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { collectDecisionReasons } from "@/lib/trading-analysis/reason-labels";
import { hasDirectionalSetup } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";

type DecisionReasonsCardProps = {
  analysis: MultiTimeframeAnalysis;
  eligibility?: ExecutionCandidateStatus | null;
};

export const DecisionReasonsCard = ({
  analysis,
  eligibility,
}: DecisionReasonsCardProps) => {
  const [showRaw, setShowRaw] = useState(false);
  const items = collectDecisionReasons({
    analysisReasons: analysis.reasons,
    analysisWarnings: analysis.warnings,
    eligibilityReasons: eligibility?.reasons,
    finalSignal: analysis.finalSignal,
    setupState: eligibility?.setupState ?? analysis.setup?.state,
  });
  const hasSetup = hasDirectionalSetup(analysis);
  const isBlocked =
    analysis.executionAssessment === "BLOCKED" ||
    (eligibility != null && !eligibility.eligible && hasSetup);

  const title =
    analysis.finalSignal === "WAIT"
      ? L.reasonsTitleWait
      : isBlocked
        ? L.reasonsTitleBlocked
        : L.reasonsTitle;

  return (
    <section className="border-t border-slate-200 pt-3" aria-label={title}>
      <h3
        className={cn(
          "text-[11px] font-semibold uppercase tracking-wide",
          isBlocked ? "text-rose-800" : "text-slate-500",
        )}
      >
        {title}
      </h3>

      {items.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">{L.dash}</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm text-slate-700">
          {items.map((item) => (
            <li key={item.code}>{item.label}</li>
          ))}
        </ul>
      )}

      {items.length > 0 ? (
        <div className="mt-2">
          <button
            type="button"
            className="text-[11px] text-slate-400 underline-offset-2 hover:text-slate-700 hover:underline"
            onClick={() => setShowRaw((v) => !v)}
            aria-expanded={showRaw}
          >
            {L.technicalDetails}
          </button>
          {showRaw ? (
            <ul className="mt-1 space-y-0.5 font-mono text-[10px] text-slate-400">
              {items.map((item) => (
                <li key={`raw-${item.code}`}>{item.code}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
};
