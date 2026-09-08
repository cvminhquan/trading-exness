import {
  MTF_LONG_THRESHOLD,
  MTF_SHORT_THRESHOLD,
} from "@/lib/trading-analysis/mtf-display";
import { TRADE_ANALYSIS_UX as L } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type MtfScoreBarProps = {
  score: number | null;
  className?: string;
};

/** Marker trên thang -100..+100; ngưỡng SHORT/LONG cố định theo engine. */
export const MtfScoreBar = ({ score, className }: MtfScoreBarProps) => {
  const clamped =
    score == null ? 0 : Math.max(-100, Math.min(100, score));
  const pct = ((clamped + 100) / 200) * 100;
  const shortPct = ((MTF_SHORT_THRESHOLD + 100) / 200) * 100;
  const longPct = ((MTF_LONG_THRESHOLD + 100) / 200) * 100;

  return (
    <div className={cn("space-y-1.5", className)} aria-label={L.mtfScore}>
      <div className="flex justify-between text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <span>SHORT</span>
        <span>WAIT</span>
        <span>LONG</span>
      </div>
      <div className="relative h-2.5 rounded-full bg-slate-100">
        <div
          className="absolute inset-y-0 rounded-l-full bg-slate-200/80"
          style={{ left: 0, width: `${shortPct}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 bg-slate-300/70"
          style={{ left: `${shortPct}%`, width: `${longPct - shortPct}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 rounded-r-full bg-slate-200/80"
          style={{ left: `${longPct}%`, right: 0 }}
          aria-hidden
        />
        {score != null ? (
          <span
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-slate-800 bg-white shadow-sm"
            style={{ left: `${pct}%` }}
            title={String(score)}
            aria-label={`${L.mtfScore} ${score}`}
          />
        ) : null}
      </div>
      <div className="flex justify-between font-mono text-[10px] text-slate-400">
        <span>-100</span>
        <span>{MTF_SHORT_THRESHOLD}</span>
        <span>0</span>
        <span>+{MTF_LONG_THRESHOLD}</span>
        <span>+100</span>
      </div>
    </div>
  );
};
