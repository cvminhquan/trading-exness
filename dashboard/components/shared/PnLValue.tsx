import { cn } from "@/lib/utils";
import {
  formatCurrency,
  formatPnLLabel,
  formatSignedCurrency,
  getPnLSentiment,
} from "@/lib/format";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

type PnLValueProps = {
  value: number | null | undefined;
  className?: string;
  showLabel?: boolean;
  showIcon?: boolean;
  size?: "sm" | "md";
};

export const PnLValue = ({
  value,
  className,
  showLabel = false,
  showIcon = true,
  size = "md",
}: PnLValueProps) => {
  const sentiment = getPnLSentiment(value);
  const formatted =
    value === null || value === undefined ? "—" : formatSignedCurrency(value);
  const label = formatPnLLabel(value);

  const Icon =
    sentiment === "profit" ? ArrowUpRight : sentiment === "loss" ? ArrowDownRight : Minus;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 tabular-nums font-medium",
        sentiment === "profit" && "text-[var(--positive)]",
        sentiment === "loss" && "text-[var(--negative)]",
        sentiment === "flat" && "text-[var(--text-muted)]",
        size === "sm" ? "text-[14px]" : "text-[16px]",
        className,
      )}
    >
      {showIcon ? <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden /> : null}
      <span aria-label={`${label}: ${formatCurrency(value ?? 0)}`}>{formatted}</span>
      {showLabel ? (
        <span className="text-xs font-normal uppercase tracking-wide text-slate-500">{label}</span>
      ) : null}
    </span>
  );
};
