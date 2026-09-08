"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Plus, X } from "lucide-react";
import { MarketMove } from "@/components/market/MarketMove";
import { MiniSparkline } from "@/components/market/MiniSparkline";
import { useSessionQuoteMoves } from "@/hooks/use-session-quote-moves";
import {
  useDashboardSymbolSignals,
  useQuotes,
} from "@/queries/use-trading-queries";
import {
  DASHBOARD_SYMBOLS,
  dashboardSymbolHref,
  isValidMarketSymbol,
  normalizeDashboardSymbol,
} from "@/lib/symbols/config";
import {
  MAX_EXTRA_SYMBOLS,
  loadExtraSymbols,
  mergeWatchSymbols,
  normalizeSymbol,
  saveExtraSymbols,
} from "@/lib/market/trending";
import { formatCompactMarketPrice } from "@/lib/format";
import { quoteMidPrice } from "@/lib/market/quote-price";
import { SYMBOL_TABS, TRENDING_QUOTES } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type SymbolTabsProps = {
  activeSymbol: string;
  hrefForSymbol?: (symbol: string) => string;
  /** Optional override; mặc định tự fetch signal mọi symbol. */
  signals?: Record<string, string | undefined>;
};

export const SymbolTabs = ({
  activeSymbol,
  hrefForSymbol = dashboardSymbolHref,
  signals: signalsOverride,
}: SymbolTabsProps) => {
  const router = useRouter();
  const sparkUid = useId().replace(/:/g, "");
  const [extras, setExtras] = useState(() => loadExtraSymbols());
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const activeRef = useRef<HTMLAnchorElement | null>(null);

  const symbols = mergeWatchSymbols(extras);
  const quotesQuery = useQuotes(symbols);
  const quotes = quotesQuery.data ?? [];
  const bySymbol = new Map(quotes.map((q) => [q.symbol, q] as const));
  const session = useSessionQuoteMoves(quotes);
  const fetchedSignals = useDashboardSymbolSignals(symbols);
  const extrasSet = new Set(extras);

  useEffect(() => {
    activeRef.current?.scrollIntoView({
      behavior: "smooth",
      inline: "nearest",
      block: "nearest",
    });
  }, [activeSymbol]);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  const handleAdd = (event?: FormEvent) => {
    event?.preventDefault();
    const symbol = normalizeSymbol(draft);
    if (!symbol || !isValidMarketSymbol(symbol)) {
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
    setAdding(false);
    router.push(hrefForSymbol(symbol));
  };

  const handleRemove = (symbol: string) => {
    const next = extras.filter((item) => item !== symbol);
    setExtras(next);
    saveExtraSymbols(next);
    if (normalizeDashboardSymbol(activeSymbol) === symbol) {
      router.push(hrefForSymbol(DASHBOARD_SYMBOLS[0]));
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setAdding(false);
      setDraft("");
      setFormError(null);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      handleAdd();
    }
  };

  return (
    <nav
      aria-label={SYMBOL_TABS.navLabel}
      className="w-full rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-card)]"
    >
      <div className="flex w-full min-w-0 items-stretch overflow-x-auto p-1">
        {symbols.map((symbol, index) => {
          const active = symbol === activeSymbol;
          const quote = bySymbol.get(symbol);
          const price = quote ? quoteMidPrice(quote) : null;
          const digits = quote?.digits ?? 2;
          const state = session[symbol];
          const move = state?.move ?? null;
          const series = state?.series ?? [];
          const signal =
            signalsOverride?.[symbol] ?? fetchedSignals[symbol] ?? undefined;
          const removable = extrasSet.has(symbol);
          const nextActive = symbols[index + 1] === activeSymbol;
          const showDivider =
            index < symbols.length - 1 && !active && !nextActive;

          const sparkTone =
            series.length >= 2
              ? series[series.length - 1]! > series[0]!
                ? "up"
                : series[series.length - 1]! < series[0]!
                  ? "down"
                  : "flat"
              : "flat";

          return (
            <div
              key={symbol}
              className={cn(
                "relative flex min-w-[10.5rem] flex-1",
                showDivider && "border-r border-[var(--border)]",
                active && "z-[1]",
              )}
            >
              <Link
                ref={active ? activeRef : undefined}
                href={hrefForSymbol(symbol)}
                className={cn(
                  "flex w-full min-w-0 flex-col gap-1 px-3.5 py-3 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                  active
                    ? "rounded-[var(--radius-tab)] bg-[var(--surface)] shadow-[inset_3px_0_0_0_var(--accent),inset_0_-3px_0_0_var(--accent),0_4px_14px_rgba(37,99,235,0.14)]"
                    : "rounded-[var(--radius-tab)] hover:bg-[var(--surface-subtle)]",
                )}
                aria-current={active ? "page" : undefined}
              >
                <div className="flex min-w-0 items-center gap-1.5 pr-4">
                  <p
                    className={cn(
                      "truncate text-[13px] tracking-wide",
                      active
                        ? "font-bold text-[var(--accent)]"
                        : "font-semibold text-[var(--foreground)]",
                    )}
                  >
                    {symbol}
                  </p>
                  <SignalBadge signal={signal} />
                </div>

                <div className="flex min-w-0 items-end justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-[17px] font-bold tabular-nums text-[var(--foreground)]">
                      {price == null
                        ? "—"
                        : `$${formatCompactMarketPrice(price, Math.min(digits, 2))}`}
                    </p>
                    {move ? (
                      <MarketMove
                        className="mt-0.5"
                        compact
                        abs={move.abs}
                        pct={move.pct}
                        absAsPrice
                        priceDigits={Math.min(digits, 2)}
                      />
                    ) : (
                      <p className="mt-0.5 text-[12px] text-[var(--muted)]">—</p>
                    )}
                  </div>
                  <MiniSparkline
                    values={series}
                    tone={sparkTone}
                    className="mb-0.5"
                    gradientKey={`${sparkUid}-${symbol}`}
                  />
                </div>
              </Link>

              {removable ? (
                <button
                  type="button"
                  onClick={() => handleRemove(symbol)}
                  className="absolute top-2 right-1.5 rounded-full p-0.5 text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                  aria-label={SYMBOL_TABS.removeTab(symbol)}
                >
                  <X className="h-3 w-3" aria-hidden />
                </button>
              ) : null}
            </div>
          );
        })}

        <div className="flex shrink-0 items-center border-l border-[var(--border)] px-3 py-2">
          {adding ? (
            <form
              onSubmit={handleAdd}
              className="flex min-w-[12rem] flex-col gap-1.5"
              aria-label={SYMBOL_TABS.addTabAria}
            >
              <input
                ref={inputRef}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value.toUpperCase());
                  setFormError(null);
                }}
                onKeyDown={handleKeyDown}
                placeholder={SYMBOL_TABS.addPlaceholder}
                aria-label={TRENDING_QUOTES.addLabel}
                aria-invalid={Boolean(formError)}
                className="h-8 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] px-2 text-[13px] font-semibold uppercase tracking-wide text-[var(--foreground)] placeholder:normal-case placeholder:tracking-normal placeholder:text-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                autoComplete="off"
                spellCheck={false}
              />
              <div className="flex items-center gap-1.5">
                <button
                  type="submit"
                  className="inline-flex h-7 flex-1 items-center justify-center gap-1 rounded-[var(--radius-control)] bg-[var(--accent)] px-2 text-[12px] font-semibold text-white hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                  {TRENDING_QUOTES.addButton}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAdding(false);
                    setDraft("");
                    setFormError(null);
                  }}
                  className="inline-flex h-7 items-center justify-center rounded-[var(--radius-control)] px-2 text-[12px] font-medium text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                  aria-label={SYMBOL_TABS.cancelAdd}
                >
                  <X className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
              {formError ? (
                <p className="text-[11px] text-[var(--negative)]" role="alert">
                  {formError}
                </p>
              ) : null}
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-control)] border border-[var(--accent)] px-3 text-[13px] font-semibold whitespace-nowrap text-[var(--accent)] transition-colors hover:bg-[var(--accent-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              aria-label={SYMBOL_TABS.addTabAria}
            >
              <Plus className="h-4 w-4" aria-hidden strokeWidth={2.25} />
              {SYMBOL_TABS.addTab}
            </button>
          )}
        </div>
      </div>
    </nav>
  );
};

const SignalBadge = ({ signal }: { signal: string | undefined }) => {
  if (!signal) {
    return (
      <span className="text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
        …
      </span>
    );
  }

  return (
    <span
      className={cn(
        "shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide",
        signal === "SHORT" &&
          "bg-[var(--negative-subtle)] text-[var(--negative)]",
        signal === "LONG" &&
          "bg-[var(--positive-subtle)] text-[var(--positive)]",
        signal === "WAIT" &&
          "bg-[var(--surface-subtle)] text-[var(--muted)]",
      )}
    >
      {signal}
    </span>
  );
};
