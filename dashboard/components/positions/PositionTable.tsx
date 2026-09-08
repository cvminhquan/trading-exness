import type { Position } from "@/domain";
import { formatDuration, formatPrice, formatRMultiple, formatVolume } from "@/lib/format";
import { METRICS, UI } from "@/lib/i18n/vi";
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
import { TableSkeleton } from "@/components/shared/Skeletons";

type PositionTableProps = {
  positions: Position[];
  compact?: boolean;
  isLoading?: boolean;
};

export const PositionTable = ({
  positions,
  compact = false,
  isLoading = false,
}: PositionTableProps) => {
  if (isLoading) return <TableSkeleton rows={compact ? 2 : 4} />;

  return (
    <div className="max-h-[420px] overflow-auto border-t border-slate-200">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-[#f4f5f7]">
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-8 text-[11px] font-medium">{UI.symbol}</TableHead>
            <TableHead className="h-8 text-[11px] font-medium">{UI.direction}</TableHead>
            <TableHead className="h-8 text-right text-[11px] font-medium">
              {UI.volume}
            </TableHead>
            <TableHead className="h-8 text-right text-[11px] font-medium">
              {UI.entry}
            </TableHead>
            <TableHead className="h-8 text-right text-[11px] font-medium">
              {UI.currentPrice}
            </TableHead>
            {!compact ? (
              <TableHead className="hidden h-8 text-right text-[11px] font-medium lg:table-cell">
                SL
              </TableHead>
            ) : null}
            {!compact ? (
              <TableHead className="hidden h-8 text-right text-[11px] font-medium lg:table-cell">
                TP
              </TableHead>
            ) : null}
            <TableHead className="h-8 text-right text-[11px] font-medium">
              {METRICS.unrealizedPnl}
            </TableHead>
            {!compact ? (
              <TableHead className="hidden h-8 text-right text-[11px] font-medium md:table-cell">
                R
              </TableHead>
            ) : null}
            <TableHead className="h-8 text-right text-[11px] font-medium">
              {UI.duration}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {positions.map((position) => (
            <TableRow key={position.id} className="h-9 hover:bg-slate-50/80">
              <TableCell className="py-1.5 text-sm font-medium">
                {position.symbol}
              </TableCell>
              <TableCell className="py-1.5">
                <DirectionIndicator direction={position.direction} />
              </TableCell>
              <TableCell className="py-1.5 text-right text-sm tabular-nums">
                {formatVolume(position.volume)}
              </TableCell>
              <TableCell className="py-1.5 text-right text-sm tabular-nums">
                {formatPrice(position.entryPrice)}
              </TableCell>
              <TableCell className="py-1.5 text-right text-sm tabular-nums">
                {formatPrice(position.currentPrice)}
              </TableCell>
              {!compact ? (
                <TableCell className="hidden py-1.5 text-right text-sm tabular-nums lg:table-cell">
                  {position.stopLoss ? formatPrice(position.stopLoss) : "—"}
                </TableCell>
              ) : null}
              {!compact ? (
                <TableCell className="hidden py-1.5 text-right text-sm tabular-nums lg:table-cell">
                  {position.takeProfit ? formatPrice(position.takeProfit) : "—"}
                </TableCell>
              ) : null}
              <TableCell className="py-1.5 text-right">
                <PnLValue value={position.unrealizedPnl} size="sm" />
              </TableCell>
              {!compact ? (
                <TableCell className="hidden py-1.5 text-right text-sm tabular-nums md:table-cell">
                  {formatRMultiple(position.rMultiple)}
                </TableCell>
              ) : null}
              <TableCell className="py-1.5 text-right text-sm tabular-nums text-slate-500">
                {formatDuration(position.openedAt)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
