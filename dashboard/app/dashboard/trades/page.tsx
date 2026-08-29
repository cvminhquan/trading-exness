"use client";

import { useMemo, useState } from "react";
import { Input, Label, Select } from "@/components/ui/input";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { TradeTable } from "@/components/trades/TradeTable";
import type { Trade } from "@/domain";
import { A11Y, DIRECTION_LABELS, EMPTY, NAV, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { useTrades } from "@/queries/use-trading-queries";
import { Search } from "lucide-react";

export default function TradesPage() {
  const { data, isLoading, isError, error, refetch } = useTrades();
  const [query, setQuery] = useState("");
  const [symbol, setSymbol] = useState("ALL");
  const [direction, setDirection] = useState("ALL");
  const [strategy, setStrategy] = useState("ALL");
  const [result, setResult] = useState("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.filter((trade: Trade) => {
      if (q && !trade.id.toLowerCase().includes(q) && !trade.symbol.toLowerCase().includes(q)) {
        return false;
      }
      if (symbol !== "ALL" && trade.symbol !== symbol) return false;
      if (direction !== "ALL" && trade.direction !== direction) return false;
      if (strategy !== "ALL" && trade.strategy !== strategy) return false;
      if (result === "WIN" && trade.netPnl <= 0) return false;
      if (result === "LOSS" && trade.netPnl >= 0) return false;
      if (dateFrom && trade.closedAt < `${dateFrom}T00:00:00.000Z`) return false;
      if (dateTo && trade.closedAt > `${dateTo}T23:59:59.999Z`) return false;
      return true;
    });
  }, [data, query, symbol, direction, strategy, result, dateFrom, dateTo]);

  const symbols = [...new Set(data?.map((t) => t.symbol) ?? [])];
  const strategies = [...new Set(data?.map((t) => t.strategy) ?? [])];

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.trades.label}
        description={NAV.trades.description}
      />

      <section
        aria-label={A11Y.tradeFilters}
        className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
      >
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
          <Search className="h-4 w-4" aria-hidden />
          {UI.filterJournal}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7">
          <div className="xl:col-span-2">
            <Label htmlFor="trade-search">{UI.search}</Label>
            <Input
              id="trade-search"
              placeholder={UI.symbolOrTradeId}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="symbol-filter">{UI.symbol}</Label>
            <Select id="symbol-filter" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              <option value="ALL">{UI.all}</option>
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="direction-filter">{UI.direction}</Label>
            <Select
              id="direction-filter"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="ALL">{UI.all}</option>
              <option value="LONG">{DIRECTION_LABELS.LONG}</option>
              <option value="SHORT">{DIRECTION_LABELS.SHORT}</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="strategy-filter">{UI.strategy}</Label>
            <Select
              id="strategy-filter"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              <option value="ALL">{UI.all}</option>
              {strategies.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="result-filter">{UI.result}</Label>
            <Select id="result-filter" value={result} onChange={(e) => setResult(e.target.value)}>
              <option value="ALL">{UI.all}</option>
              <option value="WIN">{UI.winners}</option>
              <option value="LOSS">{UI.losers}</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="date-from">{UI.from}</Label>
            <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="date-to">{UI.to}</Label>
            <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {UI.showingTrades(filtered.length, data?.length ?? 0)}
        </p>
      </section>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        isEmpty={!isLoading && filtered.length === 0}
        emptyTitle={EMPTY.noTradesMatchFilters}
        emptyDescription={EMPTY.noTradesMatchFiltersDescription}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={6} />}
        section={SECTION_LABELS.trades}
      >
        <TradeTable trades={filtered} />
      </QueryState>
    </div>
  );
}
