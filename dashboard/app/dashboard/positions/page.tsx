"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { PositionTable } from "@/components/positions/PositionTable";
import { Badge } from "@/components/ui/badge";
import { Label, Select } from "@/components/ui/input";
import { formatCurrency } from "@/lib/format";
import {
  DIRECTION_LABELS,
  EMPTY,
  METRICS,
  NAV,
  SECTION_LABELS,
  UI,
} from "@/lib/i18n/vi";
import {
  DASHBOARD_SYMBOLS,
  resolveDashboardSymbol,
} from "@/lib/symbols/config";
import { usePositions } from "@/queries/use-trading-queries";

const PositionsContent = () => {
  const searchParams = useSearchParams();
  const initialSymbol = searchParams.get("symbol");
  const [symbolFilter, setSymbolFilter] = useState(
    initialSymbol ? resolveDashboardSymbol(initialSymbol) : "ALL",
  );
  const [directionFilter, setDirectionFilter] = useState("ALL");

  const { data, isLoading, isError, error, refetch } = usePositions();

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.filter((p) => {
      if (symbolFilter !== "ALL" && p.symbol !== symbolFilter) return false;
      if (directionFilter !== "ALL" && p.direction !== directionFilter)
        return false;
      return true;
    });
  }, [data, symbolFilter, directionFilter]);

  const summary = useMemo(() => {
    const list = filtered;
    const longVol = list
      .filter((p) => p.direction === "LONG")
      .reduce((s, p) => s + p.volume, 0);
    const shortVol = list
      .filter((p) => p.direction === "SHORT")
      .reduce((s, p) => s + p.volume, 0);
    const unrealized = list.reduce((s, p) => s + p.unrealizedPnl, 0);
    return {
      openCount: list.length,
      longVol,
      shortVol,
      unrealized,
    };
  }, [filtered]);

  return (
    <>
      <section
        aria-label="Bộ lọc vị thế"
        className="flex flex-wrap items-end gap-3 border-b border-slate-200 pb-3"
      >
        <div className="min-w-[8rem]">
          <Label htmlFor="pos-symbol">{UI.symbol}</Label>
          <Select
            id="pos-symbol"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
          >
            <option value="ALL">{UI.all}</option>
            {DASHBOARD_SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="min-w-[8rem]">
          <Label htmlFor="pos-direction">{UI.direction}</Label>
          <Select
            id="pos-direction"
            value={directionFilter}
            onChange={(e) => setDirectionFilter(e.target.value)}
          >
            <option value="ALL">{UI.all}</option>
            <option value="LONG">{DIRECTION_LABELS.LONG}</option>
            <option value="SHORT">{DIRECTION_LABELS.SHORT}</option>
          </Select>
        </div>
      </section>

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-slate-500">
          Mở{" "}
          <span className="font-semibold tabular-nums text-slate-900">
            {summary.openCount}
          </span>
        </span>
        <span className="text-slate-500">
          Long{" "}
          <span className="font-semibold tabular-nums text-slate-900">
            {summary.longVol.toFixed(2)}
          </span>
        </span>
        <span className="text-slate-500">
          Short{" "}
          <span className="font-semibold tabular-nums text-slate-900">
            {summary.shortVol.toFixed(2)}
          </span>
        </span>
        <span className="text-slate-500">
          {METRICS.unrealizedPnl}{" "}
          <span className="font-semibold tabular-nums text-slate-900">
            {formatCurrency(summary.unrealized)}
          </span>
        </span>
      </div>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        isEmpty={!!data && filtered.length === 0}
        emptyTitle={EMPTY.noOpenPositions}
        emptyDescription={EMPTY.noOpenPositionsPage}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={4} />}
        section={SECTION_LABELS.positions}
      >
        {filtered.length > 0 ? <PositionTable positions={filtered} /> : null}
      </QueryState>

      <section
        className="border-t border-dashed border-slate-200 pt-3"
        aria-label="Vị thế đã đóng"
      >
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Vị thế đã đóng
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Backend hiện chưa cung cấp lịch sử vị thế đã đóng.
        </p>
      </section>
    </>
  );
};

export default function PositionsPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title={NAV.positions.label}
        description={NAV.positions.description}
        badge={
          <Badge variant="info" className="normal-case">
            {UI.readOnly} · BROKER ACCOUNT
          </Badge>
        }
      />

      <Suspense fallback={<TableSkeleton rows={4} />}>
        <PositionsContent />
      </Suspense>
    </div>
  );
}
