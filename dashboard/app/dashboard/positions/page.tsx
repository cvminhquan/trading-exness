"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Settings2 } from "lucide-react";
import { CloseConfirmDialog } from "@/components/positions/CloseConfirmDialog";
import { ClosedTradesSection } from "@/components/positions/ClosedTradesSection";
import { PositionTable } from "@/components/positions/PositionTable";
import { MetricCard, MetricStrip } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label, Select } from "@/components/ui/input";
import type { Position } from "@/domain";
import {
  formatCurrency,
  formatSignedPercent,
  formatVolume,
  getPnLSentiment,
} from "@/lib/format";
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
import { cn } from "@/lib/utils";
import {
  useAccountSnapshot,
  useAccountSwitchState,
  useClosePosition,
  useClosePositions,
  usePositions,
} from "@/queries/use-trading-queries";
import { ApiError } from "@/lib/api/errors";

type CloseIntent =
  | { kind: "one"; position: Position }
  | { kind: "bulk"; ids: string[]; mode: "selected" | "all" };

const PositionsContent = () => {
  const searchParams = useSearchParams();
  const initialSymbol = searchParams.get("symbol");
  const [symbolFilter, setSymbolFilter] = useState(
    initialSymbol ? resolveDashboardSymbol(initialSymbol) : "ALL",
  );
  const [directionFilter, setDirectionFilter] = useState("ALL");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [intent, setIntent] = useState<CloseIntent | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = usePositions();
  const { data: account } = useAccountSnapshot();
  const { data: accountSwitch } = useAccountSwitchState();
  const closeOne = useClosePosition();
  const closeBulk = useClosePositions();

  const isLive = accountSwitch?.activeProfile === "live";
  const isPending = closeOne.isPending || closeBulk.isPending;

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
    const long = list.filter((p) => p.direction === "LONG");
    const short = list.filter((p) => p.direction === "SHORT");
    const longVol = long.reduce((s, p) => s + p.volume, 0);
    const shortVol = short.reduce((s, p) => s + p.volume, 0);
    const totalVol = longVol + shortVol;
    const unrealized = list.reduce((s, p) => s + p.unrealizedPnl, 0);
    const equity = account?.equity ?? 0;
    const unrealizedPct = equity > 0 ? (unrealized / equity) * 100 : null;
    return {
      openCount: list.length,
      longVol,
      shortVol,
      longCount: long.length,
      shortCount: short.length,
      totalVol,
      unrealized,
      unrealizedPct,
    };
  }, [filtered, account?.equity]);

  const confirmPhrase = (() => {
    if (!intent) return UI.closeConfirmPhraseDemo;
    if (intent.kind === "one") {
      return isLive ? UI.closeConfirmPhraseLive : UI.closeConfirmPhraseDemo;
    }
    return isLive ? UI.closeConfirmPhraseLiveAll : UI.closeConfirmPhraseDemoAll;
  })();

  const confirmBody = (() => {
    if (!intent) return "";
    if (intent.kind === "one") {
      return UI.closeConfirmBodyOne(intent.position.symbol, intent.position.id);
    }
    if (intent.mode === "all") {
      return UI.closeConfirmBodyAll(intent.ids.length);
    }
    return UI.closeConfirmBodySelected(intent.ids.length);
  })();

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    setSelectedIds((prev) => {
      const allSelected =
        filtered.length > 0 && filtered.every((p) => prev.has(p.id));
      if (allSelected) return new Set();
      return new Set(filtered.map((p) => p.id));
    });
  };

  const handleConfirmClose = async (confirm: string) => {
    if (!intent) return;
    setCloseError(null);
    try {
      let result;
      if (intent.kind === "one") {
        result = await closeOne.mutateAsync({
          id: intent.position.id,
          confirm,
        });
      } else {
        result = await closeBulk.mutateAsync({
          confirm,
          positionIds: intent.ids,
        });
      }
      setSelectedIds(new Set());
      setIntent(null);
      window.alert(UI.closeSuccess(result.closed, result.failed));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : UI.closeFailed;
      setCloseError(message);
    }
  };

  const unrealizedSentiment = getPnLSentiment(summary.unrealized);

  return (
    <>
      <MetricStrip className="xl:grid-cols-5">
        <MetricCard
          label={METRICS.unrealizedPnl}
          value={formatCurrency(summary.unrealized)}
          secondaryValue={
            summary.unrealizedPct != null
              ? formatSignedPercent(summary.unrealizedPct)
              : undefined
          }
          trend={
            unrealizedSentiment === "profit"
              ? "up"
              : unrealizedSentiment === "loss"
                ? "down"
                : "neutral"
          }
        />
        <MetricCard
          label={UI.totalVolume}
          value={formatVolume(summary.totalVol)}
          hint={UI.lots}
        />
        <MetricCard
          label={UI.longPositions}
          value={formatVolume(summary.longVol)}
          secondaryValue={UI.positionsCount(summary.longCount)}
        />
        <MetricCard
          label={UI.shortPositions}
          value={formatVolume(summary.shortVol)}
          secondaryValue={UI.positionsCount(summary.shortCount)}
        />
        <MetricCard
          label={UI.totalPositions}
          value={String(summary.openCount)}
        />
      </MetricStrip>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle>{UI.openPositions}</CardTitle>
          </div>
          <div className="flex flex-wrap items-end gap-3">
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
            <div className="flex items-center gap-2">
              {selectedIds.size > 0 ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCloseError(null);
                    setIntent({
                      kind: "bulk",
                      ids: [...selectedIds],
                      mode: "selected",
                    });
                  }}
                  disabled={isPending || filtered.length === 0}
                >
                  {UI.closeSelected} ({selectedIds.size})
                </Button>
              ) : null}
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => {
                  setCloseError(null);
                  setIntent({
                    kind: "bulk",
                    ids: filtered.map((p) => p.id),
                    mode: "all",
                  });
                }}
                disabled={isPending || filtered.length === 0}
                aria-label={UI.closeAll}
              >
                {UI.closeAll}
              </Button>
              <Link
                href="/dashboard/settings"
                className={cn(
                  "inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)]",
                  "border border-[var(--border-strong)] text-[var(--foreground-secondary)]",
                  "hover:bg-[var(--surface-hover)]",
                )}
                aria-label={NAV.settings.label}
              >
                <Settings2 className="h-4 w-4" aria-hidden />
              </Link>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-2">
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
            {filtered.length > 0 ? (
              <PositionTable
                positions={filtered}
                selectedIds={selectedIds}
                onToggleSelect={handleToggleSelect}
                onToggleSelectAll={handleToggleSelectAll}
                onCloseOne={(position) => {
                  setCloseError(null);
                  setIntent({ kind: "one", position });
                }}
                closingId={
                  closeOne.isPending && intent?.kind === "one"
                    ? intent.position.id
                    : null
                }
              />
            ) : null}
          </QueryState>
        </CardContent>
      </Card>

      <ClosedTradesSection initialSymbol={symbolFilter} />

      <CloseConfirmDialog
        open={intent != null}
        title={UI.closeConfirmTitle}
        body={confirmBody}
        phrase={confirmPhrase}
        isPending={isPending}
        errorMessage={closeError}
        onCancel={() => {
          if (!isPending) {
            setIntent(null);
            setCloseError(null);
          }
        }}
        onConfirm={(confirm) => void handleConfirmClose(confirm)}
      />
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
            {UI.operatorClose} · BROKER ACCOUNT
          </Badge>
        }
      />

      <Suspense fallback={<TableSkeleton rows={4} />}>
        <PositionsContent />
      </Suspense>
    </div>
  );
}
