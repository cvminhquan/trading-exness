"use client";

import type { Quote } from "@/domain";
import { formatDateTime, formatMarketPrice } from "@/lib/format";
import { A11Y, METRICS, QUOTE_FRESHNESS_LABELS, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { FreshnessIndicator } from "@/components/shared/BotStatusIndicator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { aggregateQuoteFreshness } from "@/lib/market/freshness";

type WatchlistTableProps = {
  quotes: Quote[];
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  onRetry: () => void;
};

export const WatchlistTable = ({
  quotes,
  isLoading,
  isError,
  errorMessage,
  onRetry,
}: WatchlistTableProps) => {
  const freshness = aggregateQuoteFreshness(quotes);

  return (
    <QueryState
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      onRetry={onRetry}
      loadingFallback={<TableSkeleton rows={6} />}
      section={SECTION_LABELS.quotes}
      isEmpty={!isLoading && !isError && quotes.length === 0}
      emptyTitle={UI.noData}
      emptyDescription={UI.noDataDescription}
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>{METRICS.liveQuotes}</CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              Bid / Ask từ MT5 · cập nhật mỗi 2 giây. Chiến lược V1 vẫn chỉ giao dịch XAUUSD M15.
            </p>
          </div>
          <FreshnessIndicator freshness={freshness} />
        </CardHeader>
        <CardContent className="p-0 pt-0">
          <div className="overflow-auto" role="region" aria-label={A11Y.liveQuotes}>
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-white/95 backdrop-blur">
                <TableRow>
                  <TableHead>{UI.symbol}</TableHead>
                  <TableHead className="text-right">{UI.bid}</TableHead>
                  <TableHead className="text-right">{UI.ask}</TableHead>
                  <TableHead className="text-right">{UI.last}</TableHead>
                  <TableHead className="text-right">{UI.spread}</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">{UI.time}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {quotes.map((quote) => (
                  <TableRow key={quote.symbol}>
                    <TableCell className="font-medium">{quote.symbol}</TableCell>
                    {quote.available ? (
                      <>
                        <TableCell className="text-right tabular-nums">
                          {formatMarketPrice(quote.bid, quote.digits)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatMarketPrice(quote.ask, quote.digits)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatMarketPrice(quote.last, quote.digits)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-slate-600">
                          {formatMarketPrice(quote.spread, quote.digits)}
                        </TableCell>
                        <TableCell className="hidden text-right text-xs text-slate-500 sm:table-cell">
                          <span className="block">{formatDateTime(quote.updatedAt)}</span>
                          <span className="text-[11px] uppercase tracking-wide">
                            {QUOTE_FRESHNESS_LABELS[quote.freshness]}
                          </span>
                        </TableCell>
                      </>
                    ) : (
                      <TableCell colSpan={5} className="text-sm text-slate-500">
                        {UI.quoteUnavailable}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </QueryState>
  );
};
