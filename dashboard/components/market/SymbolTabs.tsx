"use client";

import Link from "next/link";
import { useQuotes } from "@/queries/use-trading-queries";
import {
  DASHBOARD_SYMBOLS,
  dashboardSymbolHref,
} from "@/lib/symbols/config";
import { formatCompactMarketPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

type SymbolTabsProps = {
  activeSymbol: string;
  hrefForSymbol?: (symbol: string) => string;
};

export const SymbolTabs = ({
  activeSymbol,
  hrefForSymbol = dashboardSymbolHref,
}: SymbolTabsProps) => {
  const symbols = [...DASHBOARD_SYMBOLS];
  const quotesQuery = useQuotes(symbols);
  const bySymbol = new Map(
    (quotesQuery.data ?? []).map((q) => [q.symbol, q] as const),
  );

  return (
    <nav
      aria-label="Symbol"
      className="-mx-1 flex gap-0 overflow-x-auto border-b border-slate-200 px-1"
    >
      {symbols.map((symbol) => {
        const active = symbol === activeSymbol;
        const quote = bySymbol.get(symbol);
        const price = quote?.last ?? quote?.bid ?? quote?.ask ?? null;
        const freshness = quote?.freshness;
        return (
          <Link
            key={symbol}
            href={hrefForSymbol(symbol)}
            className={cn(
              "min-w-[5.5rem] shrink-0 border-b-2 px-3 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
              active
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800",
            )}
            aria-current={active ? "page" : undefined}
          >
            <p
              className={cn(
                "text-[11px] tracking-wide",
                active ? "font-semibold" : "font-medium",
              )}
            >
              {symbol}
            </p>
            <p className="mt-0.5 text-sm tabular-nums text-slate-900">
              {price == null ? "—" : formatCompactMarketPrice(price)}
            </p>
            {freshness && freshness !== "LIVE" ? (
              <p className="mt-0.5 text-[10px] uppercase tracking-wide text-amber-700">
                {freshness}
              </p>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
};
