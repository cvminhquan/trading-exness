"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="space-y-6">
      <PageHeader
        title={NAV.strategy.label}
        description={NAV.strategy.description}
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
          <div className="space-y-6">
            <Card>
              <CardHeader className="flex flex-row items-start justify-between gap-4">
                <div>
                  <CardTitle>{data.name}</CardTitle>
                  <p className="text-sm text-slate-400">
                    {data.symbol} · {data.timeframe}
                  </p>
                </div>
                <Badge variant="info" className="normal-case">
                  {UI.activeStrategy}
                </Badge>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {INDICATOR_DEFS.map((ind) => (
                    <Badge key={ind.key} variant="default" className="normal-case">
                      {ind.label}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>

            <SignalCard signal={data.currentSignal} />

            <Card>
              <CardHeader>
                <CardTitle>{UI.indicatorSnapshot}</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                  {INDICATOR_DEFS.map((ind) => (
                    <div key={ind.key}>
                      <dt className="text-xs uppercase text-slate-500">{ind.label}</dt>
                      <dd className="mt-1 tabular-nums text-lg font-medium text-slate-100">
                        {formatPrice(data.currentSignal.indicators[ind.key])}
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{UI.recentSignals}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{UI.time}</TableHead>
                      <TableHead>{UI.action}</TableHead>
                      <TableHead>{UI.direction}</TableHead>
                      <TableHead>{UI.summary}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.recentSignals.map((signal) => (
                      <TableRow key={`${signal.timestamp}-${signal.action}`}>
                        <TableCell>{formatDateTime(signal.timestamp)}</TableCell>
                        <TableCell>
                          <DirectionIndicator direction={signal.action} />
                        </TableCell>
                        <TableCell>{signal.direction}</TableCell>
                        <TableCell className="max-w-xl text-slate-400">{signal.summary}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </QueryState>
    </div>
  );
}
