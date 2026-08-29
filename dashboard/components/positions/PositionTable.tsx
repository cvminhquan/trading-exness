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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TableSkeleton } from "@/components/shared/Skeletons";

type PositionTableProps = {
  positions: Position[];
  compact?: boolean;
  isLoading?: boolean;
};

export const PositionTable = ({ positions, compact = false, isLoading = false }: PositionTableProps) => {
  if (isLoading) return <TableSkeleton rows={compact ? 2 : 4} />;

  return (
    <Card>
      {!compact ? (
        <CardHeader>
          <CardTitle>{METRICS.openPositions}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className={compact ? "p-0 pt-0" : undefined}>
        <div className="max-h-[420px] overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-white/95 backdrop-blur">
              <TableRow>
                <TableHead>{UI.symbol}</TableHead>
                <TableHead>{UI.direction}</TableHead>
                <TableHead className="text-right">{UI.volume}</TableHead>
                <TableHead className="text-right">{UI.entry}</TableHead>
                <TableHead className="text-right">{UI.currentPrice}</TableHead>
                {!compact ? <TableHead className="hidden text-right lg:table-cell">SL</TableHead> : null}
                {!compact ? <TableHead className="hidden text-right lg:table-cell">TP</TableHead> : null}
                <TableHead className="text-right">{METRICS.unrealizedPnl}</TableHead>
                {!compact ? <TableHead className="hidden text-right md:table-cell">R</TableHead> : null}
                <TableHead className="text-right">{UI.duration}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((position) => (
                <TableRow key={position.id}>
                  <TableCell className="font-medium">{position.symbol}</TableCell>
                  <TableCell>
                    <DirectionIndicator direction={position.direction} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatVolume(position.volume)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatPrice(position.entryPrice)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatPrice(position.currentPrice)}</TableCell>
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums lg:table-cell">
                      {position.stopLoss ? formatPrice(position.stopLoss) : "—"}
                    </TableCell>
                  ) : null}
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums lg:table-cell">
                      {position.takeProfit ? formatPrice(position.takeProfit) : "—"}
                    </TableCell>
                  ) : null}
                  <TableCell className="text-right">
                    <PnLValue value={position.unrealizedPnl} size="sm" />
                  </TableCell>
                  {!compact ? (
                    <TableCell className="hidden text-right tabular-nums md:table-cell">
                      {formatRMultiple(position.rMultiple)}
                    </TableCell>
                  ) : null}
                  <TableCell className="text-right tabular-nums text-slate-600">
                    {formatDuration(position.openedAt)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
};
