import type { StrategySignal } from "@/domain";
import { formatDateTime, formatPrice } from "@/lib/format";
import { METRICS, UI } from "@/lib/i18n/vi";
import { DirectionIndicator } from "@/components/shared/DirectionIndicator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, XCircle } from "lucide-react";

type SignalCardProps = {
  signal: StrategySignal;
};

export const SignalCard = ({ signal }: SignalCardProps) => (
  <Card>
    <CardHeader className="flex flex-row items-start justify-between gap-4">
      <div>
        <CardTitle>{METRICS.currentSignal}</CardTitle>
        <p className="text-sm text-slate-600">
          {signal.strategy} · {signal.symbol} · {formatDateTime(signal.timestamp)}
        </p>
      </div>
      <DirectionIndicator direction={signal.action} />
    </CardHeader>
    <CardContent className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.summary}</p>
        <p className="mt-1 text-sm leading-relaxed text-slate-800">{signal.summary}</p>
      </div>

      <div>
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{UI.conditions}</p>
        <ul className="space-y-2">
          {signal.conditions.map((condition) => (
            <li
              key={condition.id}
              className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
            >
              {condition.satisfied ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-hidden />
              )}
              <div>
                <p className="text-sm font-medium text-slate-800">{condition.label}</p>
                <p className="text-xs text-slate-500">{condition.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          ["EMA 20", signal.indicators.ema20],
          ["EMA 50", signal.indicators.ema50],
          ["EMA 200", signal.indicators.ema200],
          ["RSI 14", signal.indicators.rsi14],
          ["ATR 14", signal.indicators.atr14],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="mt-1 tabular-nums text-sm font-medium text-slate-900">
              {value !== null ? formatPrice(Number(value)) : "—"}
            </dd>
          </div>
        ))}
      </dl>

      <p className="text-xs leading-relaxed text-slate-500">{signal.reason}</p>
    </CardContent>
  </Card>
);
