"use client";

import type { Position } from "@/domain";
import {
  formatDuration,
  formatPrice,
  formatRMultiple,
  formatSignedPercent,
  formatVolume,
  getPnLSentiment,
} from "@/lib/format";
import { computePositionPriceMovePct } from "@/lib/market/position-move";
import { METRICS, UI } from "@/lib/i18n/vi";
import { PnLValue } from "@/components/shared/PnLValue";
import { DirectionIndicator } from "@/components/shared/DirectionIndicator";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { cn } from "@/lib/utils";

type PositionTableProps = {
  positions: Position[];
  compact?: boolean;
  isLoading?: boolean;
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  onToggleSelectAll?: () => void;
  onCloseOne?: (position: Position) => void;
  closingId?: string | null;
};

export const PositionTable = ({
  positions,
  compact = false,
  isLoading = false,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onCloseOne,
  closingId = null,
}: PositionTableProps) => {
  if (isLoading) return <TableSkeleton rows={compact ? 2 : 4} />;

  const interactive = Boolean(onToggleSelect && selectedIds);
  const allSelected =
    interactive && positions.length > 0 && positions.every((p) => selectedIds?.has(p.id));

  return (
    <div className="max-h-[480px] overflow-auto">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-[var(--surface-subtle)]">
          <TableRow className="hover:bg-transparent">
            {interactive ? (
              <TableHead className="h-11 w-10">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleSelectAll}
                  aria-label={UI.selectAll}
                  className="h-4 w-4 accent-[var(--accent)]"
                />
              </TableHead>
            ) : null}
            <TableHead className="h-11 text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.symbol}
            </TableHead>
            <TableHead className="h-11 text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.direction}
            </TableHead>
            <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.volume}
            </TableHead>
            <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.entry}
            </TableHead>
            <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.currentPrice}
            </TableHead>
            {!compact ? (
              <TableHead className="hidden h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)] lg:table-cell">
                SL
              </TableHead>
            ) : null}
            {!compact ? (
              <TableHead className="hidden h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)] lg:table-cell">
                TP
              </TableHead>
            ) : null}
            <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {METRICS.unrealizedPnl}
            </TableHead>
            {!compact ? (
              <TableHead className="hidden h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)] md:table-cell">
                R
              </TableHead>
            ) : null}
            <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
              {UI.duration}
            </TableHead>
            {onCloseOne ? (
              <TableHead className="h-11 text-right text-[13px] font-semibold text-[var(--foreground-secondary)]">
                {UI.action}
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {positions.map((position) => {
            const movePct = computePositionPriceMovePct(position);
            const moveSentiment = getPnLSentiment(movePct);
            const selected = selectedIds?.has(position.id) ?? false;
            return (
              <TableRow
                key={position.id}
                className="h-12 border-[var(--border)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                {interactive ? (
                  <TableCell className="py-2">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => onToggleSelect?.(position.id)}
                      aria-label={`${UI.selectRow} ${position.symbol}`}
                      className="h-4 w-4 accent-[var(--accent)]"
                    />
                  </TableCell>
                ) : null}
                <TableCell className="py-2 text-[14px] font-semibold">
                  {position.symbol}
                </TableCell>
                <TableCell className="py-2">
                  <DirectionIndicator direction={position.direction} />
                </TableCell>
                <TableCell className="py-2 text-right text-[14px] tabular-nums">
                  {formatVolume(position.volume)}
                </TableCell>
                <TableCell className="py-2 text-right text-[14px] tabular-nums">
                  {formatPrice(position.entryPrice)}
                </TableCell>
                <TableCell className="py-2 text-right text-[14px] tabular-nums">
                  {formatPrice(position.currentPrice)}
                </TableCell>
                {!compact ? (
                  <TableCell className="hidden py-2 text-right text-[14px] tabular-nums lg:table-cell">
                    {position.stopLoss ? formatPrice(position.stopLoss) : "—"}
                  </TableCell>
                ) : null}
                {!compact ? (
                  <TableCell className="hidden py-2 text-right text-[14px] tabular-nums lg:table-cell">
                    {position.takeProfit ? formatPrice(position.takeProfit) : "—"}
                  </TableCell>
                ) : null}
                <TableCell className="py-2 text-right">
                  <div className="inline-flex flex-col items-end">
                    <PnLValue
                      value={position.unrealizedPnl}
                      size="sm"
                      showIcon={false}
                      className="text-[14px] font-semibold"
                    />
                    {movePct != null ? (
                      <span
                        className={cn(
                          "text-[12px] font-semibold tabular-nums",
                          moveSentiment === "profit" && "text-[var(--positive)]",
                          moveSentiment === "loss" && "text-[var(--negative)]",
                          moveSentiment === "flat" && "text-[var(--text-muted)]",
                        )}
                        title="Biến động giá so với entry (không phải ROI vốn)"
                      >
                        {formatSignedPercent(movePct)}
                      </span>
                    ) : null}
                  </div>
                </TableCell>
                {!compact ? (
                  <TableCell className="hidden py-2 text-right text-[14px] tabular-nums md:table-cell">
                    {formatRMultiple(position.rMultiple)}
                  </TableCell>
                ) : null}
                <TableCell className="py-2 text-right text-[13px] tabular-nums text-[var(--text-muted)]">
                  {formatDuration(position.openedAt)}
                </TableCell>
                {onCloseOne ? (
                  <TableCell className="py-2 text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onCloseOne(position)}
                      disabled={closingId === position.id}
                      aria-label={`${UI.close} ${position.symbol}`}
                    >
                      {closingId === position.id ? UI.closing : UI.close}
                    </Button>
                  </TableCell>
                ) : null}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};
