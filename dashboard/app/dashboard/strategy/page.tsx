"use client";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BotStatusIndicator } from "@/components/shared/BotStatusIndicator";
import { DirectionIndicator } from "@/components/shared/DirectionIndicator";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { SignalCard } from "@/components/strategy/SignalCard";
import { formatDateTime, formatPrice } from "@/lib/format";
import { NAV, SECTION_LABELS, UI } from "@/lib/i18n/vi";
import { useStrategySnapshot } from "@/queries/use-trading-queries";

const INDICATOR_DEFS = [
  { key: "ema20", label: "EMA 20" },
  { key: "ema50", label: "EMA 50" },
  { key: "ema200", label: "EMA 200" },
  { key: "rsi14", label: "RSI 14" },
  { key: "atr14", label: "ATR 14" },
] as const;

export default function StrategyPage() {
  const { data, isLoading, isError, error, refetch } = useStrategySnapshot();

  return (
    <div className="space-y-4">
      <PageHeader
        title={NAV.strategy.label}
        description="Logic đánh giá thị trường đang dùng (production) và candidate research."
        badge={data ? <BotStatusIndicator status={data.status} /> : undefined}
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={4} />}
        section={SECTION_LABELS.strategy}
      >
        {data ? (
          <div className="space-y-4">
            <section className="border-b border-slate-200 pb-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">
                    {data.name}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {data.symbol} · {data.timeframe} · mtf_technical_v1 · CURRENT /
                    PRODUCTION ANALYSIS
                  </p>
                </div>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  {UI.activeStrategy}
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Indicators: {INDICATOR_DEFS.map((i) => i.label).join(" · ")}
              </p>
            </section>

            <section className="border-b border-slate-200 pb-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">
                    mtf_technical_v2_candidate
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    M15-first research — không dùng cho execution.
                  </p>
                </div>
                <Badge variant="warning">RESEARCH ONLY</Badge>
              </div>
              <dl className="mt-2 space-y-1 text-sm text-slate-700">
                <div>
                  <dt className="inline text-xs text-slate-500">TF roles · </dt>
                  <dd className="inline">
                    M15 PRIMARY · H1 CONFIRMATION · H4 CONTEXT · D1 MACRO
                  </dd>
                </div>
                <div>
                  <dt className="inline text-xs text-slate-500">Weights · </dt>
                  <dd className="inline tabular-nums">
                    TF 0.50/0.30/0.15/0.05 · components
                    0.25/0.15/0.20/0.10/0.10/0.20 · ±20 · dampen 0.35
                  </dd>
                </div>
              </dl>
              <p className="mt-2 text-[11px] text-slate-400">
                Không có Activate / Use Strategy.
              </p>
            </section>

            <SignalCard signal={data.currentSignal} />

            <section className="border-t border-slate-200 pt-3">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {UI.indicatorSnapshot}
              </h3>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
                {INDICATOR_DEFS.map((ind) => (
                  <div key={ind.key}>
                    <dt className="text-[10px] uppercase text-slate-400">
                      {ind.label}
                    </dt>
                    <dd className="text-sm font-medium tabular-nums text-slate-900">
                      {formatPrice(data.currentSignal.indicators[ind.key])}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="border-t border-slate-200 pt-3">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {UI.recentSignals}
              </h3>
              <div className="mt-1">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-8 text-[11px]">{UI.time}</TableHead>
                      <TableHead className="h-8 text-[11px]">{UI.action}</TableHead>
                      <TableHead className="h-8 text-[11px]">{UI.direction}</TableHead>
                      <TableHead className="h-8 text-[11px]">{UI.summary}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.recentSignals.map((signal) => (
                      <TableRow key={`${signal.timestamp}-${signal.action}`}>
                        <TableCell className="py-1.5 text-sm">
                          {formatDateTime(signal.timestamp)}
                        </TableCell>
                        <TableCell className="py-1.5">
                          <DirectionIndicator direction={signal.action} />
                        </TableCell>
                        <TableCell className="py-1.5 text-sm">
                          {signal.direction}
                        </TableCell>
                        <TableCell className="max-w-xl py-1.5 text-sm text-slate-600">
                          {signal.summary}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          </div>
        ) : null}
      </QueryState>
    </div>
  );
}
