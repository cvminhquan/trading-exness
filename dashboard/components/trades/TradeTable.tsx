import type { Trade } from "@/domain";
import { formatCurrency, formatDateTime, formatPrice, formatRMultiple, formatVolume } from "@/lib/format";
import { formatExitReason, UI } from "@/lib/i18n/vi";
import { PnLValue } from "@/components/shared/PnLValue";
import { DirectionIndicator } from "@/components/shared/DirectionIndicator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TableSkeleton } from "@/components/shared/Skeletons";

type TradeTableProps = {
  trades: Trade[];
  compact?: boolean;
  isLoading?: boolean;
};

export const TradeTable = ({ trades, compact = false, isLoading = false }: TradeTableProps) => {
  if (isLoading) return <TableSkeleton rows={compact ? 3 : 6} />;

  return (
    <Card>
      {!compact ? (
        <CardHeader>
          <CardTitle>{UI.tradeJournal}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className={compact ? "p-0 pt-0" : undefined}>
        <div className="max-h-[480px] overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur">
              <TableRow>
                <TableHead>{UI.time}</TableHead>
                <TableHead>{UI.symbol}</TableHead>
                {!compact ? <TableHead className="hidden md:table-cell">{UI.strategy}</TableHead> : null}
                <TableHead>{UI.direction}</TableHead>
                <TableHead className="text-right">{UI.entry}</TableHead>
                <TableHead className="text-right">{UI.exit}</TableHead>
                <TableHead className="hidden text-right sm:table-cell">{UI.volume}</TableHead>
                {!compact ? <TableHead className="hidden text-right lg:table-cell">{UI.gross}</TableHead> : null}
                {!compact ? <TableHead className="hidden text-right lg:table-cell">{UI.costs}</TableHead> : null}
                <TableHead className="text-right">{UI.netPnl}</TableHead>
                {!compact ? <TableHead className="hidden text-right md:table-cell">R</TableHead> : null}
                {!compact ? <TableHead className="hidden text-right xl:table-cell">{UI.exitReason}</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {trades.map((trade) => (
                <TableRow key={trade.id}>
                  <TableCell className="whitespace-nowrap text-slate-300">
                    {formatDateTime(trade.closedAt)}
                  </TableCell>
                  <TableCell className="font-medium">{trade.symbol}</TableCell>
                  {!compact ? (
                    <TableCell className="hidden md:table-cell">{trade.strategy}</TableCell>
                  ) : null}
                  <TableCell>
                    <DirectionIndicator direction={trade.direction} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatPrice(trade.entryPrice)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatPrice(trade.exitPrice)}</TableCell>
                  <TableCell className="hidden text-right tabular-nums sm:table-cell">
                    {formatVolume(trade.volume)}
                  </TableCell>
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums lg:table-cell">
                      {formatCurrency(trade.grossPnl)}
                    </TableCell>
                  ) : null}
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums lg:table-cell">
                      {formatCurrency(trade.costs)}
                    </TableCell>
                  ) : null}
                  <TableCell className="text-right">
                    <PnLValue value={trade.netPnl} size="sm" />
                  </TableCell>
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums md:table-cell">
                      {formatRMultiple(trade.rMultiple)}
                    </TableCell>
                  ) : null}
                  {!compact ? (
                    <TableCell className="hidden text-right text-slate-400 xl:table-cell">
                      {formatExitReason(trade.exitReason)}
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
};
