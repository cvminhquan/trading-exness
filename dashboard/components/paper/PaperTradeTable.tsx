import type { PaperTradeRow } from "@/domain";
import { formatDateTime, formatPrice, formatVolume } from "@/lib/format";
import {
  PAPER_REASON_LABELS,
  PAPER_STATUS_LABELS,
  PAPER_TRADING,
  UI,
} from "@/lib/i18n/vi";
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
import { Badge } from "@/components/ui/badge";
import { TableSkeleton } from "@/components/shared/Skeletons";

type PaperTradeTableProps = {
  trades: PaperTradeRow[];
  isLoading?: boolean;
};

const statusLabel = (status: string): string => {
  if (status in PAPER_STATUS_LABELS) {
    return PAPER_STATUS_LABELS[status as keyof typeof PAPER_STATUS_LABELS];
  }
  return status;
};

const reasonLabel = (reason: string | null): string => {
  if (!reason) return "—";
  if (reason in PAPER_REASON_LABELS) {
    return PAPER_REASON_LABELS[reason as keyof typeof PAPER_REASON_LABELS];
  }
  return reason;
};

export const PaperTradeTable = ({ trades, isLoading = false }: PaperTradeTableProps) => {
  if (isLoading) return <TableSkeleton rows={4} />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{PAPER_TRADING.tableTitle}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-[520px] overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-white/95 backdrop-blur">
              <TableRow>
                <TableHead>{UI.time}</TableHead>
                <TableHead>{UI.symbol}</TableHead>
                <TableHead>{UI.direction}</TableHead>
                <TableHead className="text-right">{UI.volume}</TableHead>
                <TableHead className="text-right">{UI.entry}</TableHead>
                <TableHead className="hidden text-right lg:table-cell">SL</TableHead>
                <TableHead className="hidden text-right lg:table-cell">TP</TableHead>
                <TableHead className="text-right">{UI.exit}</TableHead>
                <TableHead className="text-right">{UI.netPnl}</TableHead>
                <TableHead>{PAPER_TRADING.status}</TableHead>
                <TableHead>{PAPER_TRADING.reason}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trades.map((row) => (
                <TableRow key={`${row.time}-${row.symbol}-${row.status}-${row.reason ?? ""}`}>
                  <TableCell className="whitespace-nowrap text-slate-600">
                    {formatDateTime(row.time)}
                  </TableCell>
                  <TableCell className="font-medium">{row.symbol}</TableCell>
                  <TableCell>
                    <DirectionIndicator direction={row.side} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatVolume(row.volume)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPrice(row.entry)}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums lg:table-cell">
                    {formatPrice(row.stopLoss)}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums lg:table-cell">
                    {formatPrice(row.takeProfit)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPrice(row.exit)}
                  </TableCell>
                  <TableCell className="text-right">
                    {row.pnl === null ? "—" : <PnLValue value={row.pnl} size="sm" />}
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.status === "REJECTED" ? "warning" : "info"} className="normal-case">
                      {statusLabel(row.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-slate-600">{reasonLabel(row.reason)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
};
