import { cn } from "@/lib/utils";
import {
  formatSignedMoney,
  formatSignedPercent,
  getPnLSentiment,
} from "@/lib/format";

type MarketMoveProps = {
  abs?: number | null;
  pct?: number | null;
  currency?: string;
  absAsPrice?: boolean;
  priceDigits?: number;
  className?: string;
  compact?: boolean;
};

const formatAbsPrice = (value: number, digits: number): string => {
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (value > 0) return `+$${abs}`;
  if (value < 0) return `-$${abs}`;
  return `$${abs}`;
};

export const MarketMove = ({
  abs,
  pct,
  currency = "USD",
  absAsPrice = false,
  priceDigits = 2,
  className,
  compact = false,
}: MarketMoveProps) => {
  const lead = abs ?? pct;
  if (lead == null || Number.isNaN(lead)) return null;
  const sentiment = getPnLSentiment(lead);
  const arrow =
    sentiment === "profit" ? "▲" : sentiment === "loss" ? "▼" : "•";

  return (
    <span
      className={cn(
        "inline-flex flex-wrap items-baseline gap-x-2 tabular-nums",
        compact ? "text-[12px]" : "text-[14px]",
        sentiment === "profit" && "text-[var(--positive)]",
        sentiment === "loss" && "text-[var(--negative)]",
        sentiment === "flat" && "text-[var(--text-muted)]",
        className,
      )}
    >
      <span aria-hidden>{arrow}</span>
      {abs != null ? (
        <span className="font-semibold">
          {absAsPrice
            ? formatAbsPrice(abs, priceDigits)
            : formatSignedMoney(abs, currency)}
        </span>
      ) : null}
      {pct != null ? (
        <span className="font-semibold">{formatSignedPercent(pct)}</span>
      ) : null}
    </span>
  );
};
