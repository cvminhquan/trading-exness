"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { MarketMove } from "@/components/market/MarketMove";
import { useSessionQuoteMoves } from "@/hooks/use-session-quote-moves";
import { useQuotes } from "@/queries/use-trading-queries";
import {
  DASHBOARD_SYMBOLS,
  dashboardSymbolHref,
} from "@/lib/symbols/config";
import { formatCompactMarketPrice } from "@/lib/format";
import { quoteMidPrice } from "@/lib/market/quote-price";
import { cn } from "@/lib/utils";

type SymbolTabsProps = {
  activeSymbol: string;
  hrefForSymbol?: (symbol: string) => string;
  signals?: Record<string, string | undefined>;
};

export const SymbolTabs = ({
  activeSymbol,
  hrefForSymbol = dashboardSymbolHref,
  signals,
}: SymbolTabsProps) => {
  const symbols = [...DASHBOARD_SYMBOLS];
  const quotesQuery = useQuotes(symbols);
  const quotes = quotesQuery.data ?? [];
  const bySymbol = new Map(quotes.map((q) => [q.symbol, q] as const));
  const moves = useSessionQuoteMoves(quotes);
  const activeRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({
      behavior: "smooth",
      inline: "nearest",
      block: "nearest",
    });
  }, [activeSymbol]);

  return (
    <nav
      aria-label="Symbol"
      className="surface-card overflow-hidden"
    >
      <div className="flex gap-0 overflow-x-auto">
        {symbols.map((symbol) => {
          const active = symbol === activeSymbol;
          const quote = bySymbol.get(symbol);
          const price = quote ? quoteMidPrice(quote) : null;
          const digits = quote?.digits ?? 2;
          const move = moves[symbol];
          const signal = signals?.[symbol];
          const signalTone =
            signal === "LONG"
              ? "text-[var(--positive)]"
              : signal === "SHORT"
                ? "text-[var(--negative)]"
                : "text-[var(--muted)]";

          return (
            <Link
              key={symbol}
              ref={active ? activeRef : undefined}
              href={hrefForSymbol(symbol)}
              className={cn(
                "min-w-[9rem] shrink-0 border-b-[3px] px-4 py-3 whitespace-nowrap transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-inset",
                active
                  ? "border-[var(--accent)] bg-[var(--surface-active)]"
                  : "border-transparent hover:bg-[var(--accent-subtle)]",
              )}
              aria-current={active ? "page" : undefined}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p
                  className={cn(
                    "text-[13px] tracking-wide text-[var(--foreground)]",
                    active ? "font-bold" : "font-semibold",
                  )}
                >
                  {symbol}
                </p>
                {signal && signal !== "WAIT" ? (
                  <span
                    className={cn(
                      "text-[12px] font-bold uppercase tracking-wide",
                      signalTone,
                    )}
                  >
                    {signal}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-[15px] font-semibold tabular-nums text-[var(--foreground)]">
                {price == null
                  ? "—"
                  : `$${formatCompactMarketPrice(price, Math.min(digits, 2))}`}
              </p>
              {move ? (
                <MarketMove
                  className="mt-1"
                  compact
                  abs={move.abs}
                  pct={move.pct}
                  absAsPrice
                  priceDigits={Math.min(digits, 2)}
                />
              ) : (
                <p className="mt-1 text-[12px] text-[var(--muted)]">—</p>
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
};
