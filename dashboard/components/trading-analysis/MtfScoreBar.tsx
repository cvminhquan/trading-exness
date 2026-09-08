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

/** Diverging scale −100…+100 with center 0 — not a L→R progress bar. */
export const MtfScoreBar = ({ score, className }: MtfScoreBarProps) => {
  const clamped =
    score == null ? 0 : Math.max(-100, Math.min(100, score));
  const pct = ((clamped + 100) / 200) * 100;
  const shortPct = ((MTF_SHORT_THRESHOLD + 100) / 200) * 100;
  const longPct = ((MTF_LONG_THRESHOLD + 100) / 200) * 100;
  const zeroPct = 50;

  return (
    <div className={cn("space-y-1.5", className)} aria-label={L.mtfScore}>
      <div className="relative h-2.5 rounded-full bg-[var(--surface)]">
        <div
          className="absolute inset-y-0 rounded-l-full bg-[var(--negative-subtle)]"
          style={{ left: 0, width: `${shortPct}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 bg-[var(--surface-hover)]"
          style={{ left: `${shortPct}%`, width: `${longPct - shortPct}%` }}
          aria-hidden
          title="WAIT"
        />
        <div
          className="absolute inset-y-0 rounded-r-full bg-[var(--positive-subtle)]"
          style={{ left: `${longPct}%`, right: 0 }}
          aria-hidden
        />
        <span
          className="absolute top-0 bottom-0 w-px bg-[var(--border-strong)]"
          style={{ left: `${zeroPct}%` }}
          aria-hidden
        />
        {score != null ? (
          <span
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--surface)] bg-[var(--foreground)]"
            style={{ left: `${pct}%` }}
            title={String(score)}
            aria-label={`${L.mtfScore} ${score}`}
          />
        ) : null}
      </div>
      <div className="flex justify-between text-[12px] tabular-nums text-[var(--muted)]">
        <span>-100</span>
        <span>{MTF_SHORT_THRESHOLD}</span>
        <span className="font-semibold text-[var(--foreground-secondary)]">0</span>
        <span>+{MTF_LONG_THRESHOLD}</span>
        <span>+100</span>
      </div>
    </div>
  );
};
