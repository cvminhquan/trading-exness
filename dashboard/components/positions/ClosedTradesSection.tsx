"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import type { Direction, Trade } from "@/domain";
import type { TradeListParams } from "@/domain/api/params";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { TradeTable } from "@/components/trades/TradeTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import {
  A11Y,
  DIRECTION_LABELS,
  EMPTY,
  SECTION_LABELS,
  UI,
} from "@/lib/i18n/vi";
import { DASHBOARD_SYMBOLS } from "@/lib/symbols/config";
import { useTrades } from "@/queries/use-trading-queries";

type ClosedTradesSectionProps = {
  initialSymbol?: string;
};

const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

const toCsvValue = (value: string | number): string => {
  const raw = String(value);
  if (raw.includes(",") || raw.includes('"') || raw.includes("\n")) {
    return `"${raw.replaceAll('"', '""')}"`;
  }
  return raw;
};

const downloadTradesCsv = (trades: Trade[]) => {
  const header = [
    "id",
    "closedAt",
    "symbol",
    "strategy",
    "direction",
    "entryPrice",
    "exitPrice",
    "volume",
    "grossPnl",
    "costs",
    "netPnl",
    "rMultiple",
    "exitReason",
  ];
  const rows = trades.map((t) =>
    [
      t.id,
      t.closedAt,
      t.symbol,
      t.strategy,
      t.direction,
      t.entryPrice,
      t.exitPrice,
      t.volume,
      t.grossPnl,
      t.costs,
      t.netPnl,
      t.rMultiple ?? "",
      t.exitReason,
    ]
      .map(toCsvValue)
      .join(","),
  );
  const blob = new Blob([[header.join(","), ...rows].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `closed-trades-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
};

export const ClosedTradesSection = ({
  initialSymbol = "ALL",
}: ClosedTradesSectionProps) => {
  const [query, setQuery] = useState("");
  const [symbol, setSymbol] = useState(initialSymbol);
  const [direction, setDirection] = useState("ALL");
  const [strategy, setStrategy] = useState("ALL");
  const [result, setResult] = useState("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(25);

  useEffect(() => {
    setSymbol(initialSymbol);
  }, [initialSymbol]);

  useEffect(() => {
    setPage(1);
  }, [query, symbol, direction, strategy, result, dateFrom, dateTo, pageSize]);

  const apiParams = useMemo((): TradeListParams => {
    const params: TradeListParams = { page: 1, pageSize: 200 };
    if (symbol !== "ALL") params.symbol = symbol;
    if (direction === "LONG" || direction === "SHORT") {
      params.direction = direction as Direction;
    }
    if (result === "WIN" || result === "LOSS") params.result = result;
    if (dateFrom) params.start = `${dateFrom}T00:00:00.000Z`;
    if (dateTo) params.end = `${dateTo}T23:59:59.999Z`;
    return params;
  }, [symbol, direction, result, dateFrom, dateTo]);

  const { data, isLoading, isError, error, refetch } = useTrades(apiParams);

  const strategies = useMemo(
    () => [...new Set((data ?? []).map((t) => t.strategy).filter(Boolean))],
    [data],
  );

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.filter((trade: Trade) => {
      if (
        q &&
        !trade.id.toLowerCase().includes(q) &&
        !trade.symbol.toLowerCase().includes(q)
      ) {
        return false;
      }
      if (strategy !== "ALL" && trade.strategy !== strategy) return false;
      return true;
    });
  }, [data, query, strategy]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  return (
    <Card aria-label={UI.closedTrades}>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>{UI.closedTrades}</CardTitle>
          <p className="mt-0.5 text-[12px] text-[var(--muted)]">
            {UI.closedTradesHint}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => downloadTradesCsv(filtered)}
          disabled={filtered.length === 0}
          aria-label={UI.exportCsv}
        >
          <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          {UI.exportCsv}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <section
          aria-label={A11Y.tradeFilters}
          className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface-subtle)] p-4"
        >
          <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-[var(--foreground-secondary)]">
            <Search className="h-4 w-4" aria-hidden />
            {UI.filterJournal}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7">
            <div className="xl:col-span-2">
              <Label htmlFor="closed-trade-search">{UI.search}</Label>
              <Input
                id="closed-trade-search"
                placeholder={UI.symbolOrTradeId}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="closed-symbol-filter">{UI.symbol}</Label>
              <Select
                id="closed-symbol-filter"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              >
                <option value="ALL">{UI.all}</option>
                {DASHBOARD_SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="closed-direction-filter">{UI.direction}</Label>
              <Select
                id="closed-direction-filter"
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
              >
                <option value="ALL">{UI.all}</option>
                <option value="LONG">{DIRECTION_LABELS.LONG}</option>
                <option value="SHORT">{DIRECTION_LABELS.SHORT}</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="closed-strategy-filter">{UI.strategy}</Label>
              <Select
                id="closed-strategy-filter"
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
              <Label htmlFor="closed-result-filter">{UI.result}</Label>
              <Select
                id="closed-result-filter"
                value={result}
                onChange={(e) => setResult(e.target.value)}
              >
                <option value="ALL">{UI.all}</option>
                <option value="WIN">{UI.winners}</option>
                <option value="LOSS">{UI.losers}</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="closed-date-from">{UI.from}</Label>
              <Input
                id="closed-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="closed-date-to">{UI.to}</Label>
              <Input
                id="closed-date-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
          </div>
          <p className="mt-3 text-[12px] text-[var(--muted)]">
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
          {pageRows.length > 0 ? (
            <TradeTable trades={pageRows} compact framed={false} />
          ) : null}
        </QueryState>

        {filtered.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-3">
            <div className="flex items-center gap-2 text-[13px] text-[var(--muted)]">
              <Label htmlFor="closed-page-size" className="mb-0">
                {UI.rowsPerPage}
              </Label>
              <Select
                id="closed-page-size"
                value={String(pageSize)}
                onChange={(e) =>
                  setPageSize(Number(e.target.value) as (typeof PAGE_SIZE_OPTIONS)[number])
                }
                className="w-20"
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </Select>
              <span>{UI.pageOf(currentPage, totalPages)}</span>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                {UI.previous}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                {UI.next}
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};
