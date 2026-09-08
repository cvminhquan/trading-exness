"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Plus, X } from "lucide-react";
import type { Quote } from "@/domain";
import { QueryState } from "@/components/shared/States";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  formatCompactMarketPrice,
  formatSignedPercentChange,
} from "@/lib/format";
import { A11Y, SECTION_LABELS, TRENDING_QUOTES, UI } from "@/lib/i18n/vi";
import { computeSessionChangePct, quoteMidPrice } from "@/lib/market/quote-price";
import {
  MAX_EXTRA_SYMBOLS,
  TRENDING_SYMBOLS,
  loadExtraSymbols,
  mergeWatchSymbols,
  normalizeSymbol,
  saveExtraSymbols,
} from "@/lib/market/trending";
import { cn } from "@/lib/utils";
import { useQuotes } from "@/queries/use-trading-queries";

const EMPTY_QUOTES: Quote[] = [];

const SYMBOL_COLORS: Record<string, string> = {
  XAUUSD: "bg-amber-500",
  XAGUSD: "bg-slate-400",
  BTCUSD: "bg-orange-500",
  ETHUSD: "bg-indigo-500",
  EURUSD: "bg-sky-500",
  GBPUSD: "bg-rose-500",
  USDJPY: "bg-violet-500",
};

const symbolBadgeClass = (symbol: string): string =>
  SYMBOL_COLORS[symbol] ?? "bg-slate-600";

const symbolShort = (symbol: string): string => {
  if (symbol.endsWith("USD") && symbol.length > 3) return symbol.slice(0, -3).slice(0, 3);
  return symbol.slice(0, 3);
};

const fallbackQuote = (symbol: string): Quote => ({
  symbol,
  bid: null,
  ask: null,
  last: null,
  spread: null,
  digits: 5,
  available: false,
  updatedAt: new Date(0).toISOString(),
  freshness: "UNAVAILABLE",
});

type RowProps = {
  rank: number;
  quote: Quote;
  changePct: number | null;
  removable?: boolean;
  onRemove?: () => void;
};

const QuoteRow = ({ rank, quote, changePct, removable, onRemove }: RowProps) => {
  const mid = quoteMidPrice(quote);
  const up = changePct != null && changePct > 0;
  const down = changePct != null && changePct < 0;

  return (
    <li className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50">
      <span className="w-4 shrink-0 text-center text-sm tabular-nums text-slate-400">
        {rank}
      </span>
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white",
          symbolBadgeClass(quote.symbol),
        )}
        aria-hidden
      >
        {symbolShort(quote.symbol)}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900">
        {quote.symbol}
      </span>
      <div className="flex shrink-0 flex-col items-end gap-0.5 sm:flex-row sm:items-center sm:gap-4">
        <span className="text-sm font-medium tabular-nums text-slate-800">
          {quote.available ? formatCompactMarketPrice(mid, quote.digits) : UI.quoteUnavailable}
        </span>
        <span
          className={cn(
            "inline-flex min-w-[4.5rem] items-center justify-end gap-0.5 text-xs font-semibold tabular-nums",
            up && "text-emerald-600",
            down && "text-rose-600",
            !up && !down && "text-slate-400",
          )}
          aria-label={
            changePct == null
              ? TRENDING_QUOTES.changeUnavailable
              : `${TRENDING_QUOTES.sessionChange}: ${formatSignedPercentChange(changePct)}`
          }
        >
          {changePct == null ? (
            "—"
          ) : (
            <>
              <span aria-hidden>{up ? "▲" : down ? "▼" : "•"}</span>
              {formatSignedPercentChange(changePct)}
            </>
          )}
        </span>
      </div>
      {removable ? (
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
          aria-label={TRENDING_QUOTES.removeSymbol(quote.symbol)}
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : (
        <span className="w-6 shrink-0" aria-hidden />
      )}
    </li>
  );
};

export const TrendingQuotesCard = () => {
  const [extras, setExtras] = useState(() => loadExtraSymbols());
  const [draft, setDraft] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [midSnapshot, setMidSnapshot] = useState<{
    quotesKey: string;
    changes: Record<string, number | null>;
    mids: Record<string, number>;
  }>({ quotesKey: "", changes: {}, mids: {} });

  const symbols = mergeWatchSymbols(extras);
  const quotesQuery = useQuotes(symbols);
  const quotes = quotesQuery.data ?? EMPTY_QUOTES;
  const bySymbol = new Map(quotes.map((q) => [q.symbol, q]));

  const quotesKey = quotes
    .map((q) => `${q.symbol}:${q.bid}:${q.ask}:${q.last}`)
    .join("|");

  if (quotesKey !== midSnapshot.quotesKey) {
    const nextChanges: Record<string, number | null> = {};
    const nextMids: Record<string, number> = { ...midSnapshot.mids };
    for (const quote of quotes) {
      const mid = quoteMidPrice(quote);
      if (mid == null) {
        nextChanges[quote.symbol] = null;
        continue;
      }
      nextChanges[quote.symbol] = computeSessionChangePct(
        mid,
        midSnapshot.mids[quote.symbol],
      );
      nextMids[quote.symbol] = mid;
    }
    setMidSnapshot({ quotesKey, changes: nextChanges, mids: nextMids });
  }

  const changeBySymbol = midSnapshot.changes;

  const handleAdd = (event?: FormEvent) => {
    event?.preventDefault();
    const symbol = normalizeSymbol(draft);
    if (!symbol) {
      setFormError(TRENDING_QUOTES.invalidSymbol);
      return;
    }
    if (symbols.includes(symbol)) {
      setFormError(TRENDING_QUOTES.alreadyAdded);
      return;
    }
    if (extras.length >= MAX_EXTRA_SYMBOLS) {
      setFormError(TRENDING_QUOTES.maxExtras);
      return;
    }
    const next = [...extras, symbol];
    setExtras(next);
    saveExtraSymbols(next);
    setDraft("");
    setFormError(null);
  };

  const handleRemove = (symbol: string) => {
    const next = extras.filter((item) => item !== symbol);
    setExtras(next);
    saveExtraSymbols(next);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAdd();
    }
  };

  return (
    <QueryState
      isLoading={quotesQuery.isLoading && quotes.length === 0}
      isError={quotesQuery.isError}
      errorMessage={quotesQuery.error?.message}
      onRetry={() => void quotesQuery.refetch()}
      section={SECTION_LABELS.quotes}
      isEmpty={false}
    >
      <Card className="h-full overflow-hidden">
        <CardHeader className="space-y-0 px-4 pb-2 pt-4">
          <CardTitle className="text-sm font-semibold text-slate-900">
            {TRENDING_QUOTES.title}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 px-0 pb-4 pt-0">
          <ol className="divide-y divide-slate-100" aria-label={A11Y.liveQuotes}>
            {TRENDING_SYMBOLS.map((symbol, index) => (
              <QuoteRow
                key={symbol}
                rank={index + 1}
                quote={bySymbol.get(symbol) ?? fallbackQuote(symbol)}
                changePct={changeBySymbol[symbol] ?? null}
              />
            ))}
          </ol>

          {extras.length > 0 ? (
            <div className="border-t border-slate-100 pt-1">
              <p className="px-4 pb-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {TRENDING_QUOTES.addedSection}
              </p>
              <ul className="divide-y divide-slate-100">
                {extras.map((symbol, index) => (
                  <QuoteRow
                    key={symbol}
                    rank={TRENDING_SYMBOLS.length + index + 1}
                    quote={bySymbol.get(symbol) ?? fallbackQuote(symbol)}
                    changePct={changeBySymbol[symbol] ?? null}
                    removable
                    onRemove={() => handleRemove(symbol)}
                  />
                ))}
              </ul>
            </div>
          ) : null}

          <form
            className="mx-4 flex gap-2"
            onSubmit={handleAdd}
            aria-label={TRENDING_QUOTES.addSection}
          >
            <Input
              id="add-symbol"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value.toUpperCase());
                setFormError(null);
              }}
              onKeyDown={handleKeyDown}
              placeholder={TRENDING_QUOTES.addPlaceholder}
              aria-label={TRENDING_QUOTES.addLabel}
              aria-invalid={Boolean(formError)}
              className="h-8 uppercase"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="submit"
              className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md bg-slate-900 px-2.5 text-xs font-medium text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
              aria-label={TRENDING_QUOTES.addButton}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden />
              {TRENDING_QUOTES.addButton}
            </button>
          </form>
          {formError ? (
            <p className="px-4 text-xs text-rose-600" role="alert">
              {formError}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </QueryState>
  );
};
