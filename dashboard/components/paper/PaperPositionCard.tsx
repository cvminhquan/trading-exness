import type { PaperPosition } from "@/domain";
import { formatDateTime, formatPrice, formatVolume } from "@/lib/format";
import { METRICS, PAPER_TRADING, UI } from "@/lib/i18n/vi";
import { PnLValue } from "@/components/shared/PnLValue";
import { DirectionIndicator } from "@/components/shared/DirectionIndicator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type PaperPositionCardProps = {
  position: PaperPosition;
};

export const PaperPositionCard = ({ position }: PaperPositionCardProps) => (
  <Card className="border-amber-200" aria-label={PAPER_TRADING.paperPosition}>
    <CardHeader>
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle>{PAPER_TRADING.paperPosition}</CardTitle>
        <Badge variant="warning" className="normal-case">
          {PAPER_TRADING.warning}
        </Badge>
      </div>
    </CardHeader>
    <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.symbol}</p>
        <p className="font-medium">{position.symbol}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.direction}</p>
        <DirectionIndicator direction={position.side} />
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.volume}</p>
        <p className="tabular-nums">{formatVolume(position.volume)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.entry}</p>
        <p className="tabular-nums">{formatPrice(position.entryPrice)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.currentPrice}</p>
        <p className="tabular-nums">{formatPrice(position.currentPrice)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">SL</p>
        <p className="tabular-nums">{formatPrice(position.stopLoss)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">TP</p>
        <p className="tabular-nums">{formatPrice(position.takeProfit)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{METRICS.unrealizedPnl}</p>
        <PnLValue value={position.unrealizedPnl} size="sm" />
      </div>
      <div className="sm:col-span-2">
        <p className="text-xs uppercase tracking-wide text-slate-500">{UI.time}</p>
        <p className="text-sm text-slate-600">{formatDateTime(position.openedAt)}</p>
      </div>
    </CardContent>
  </Card>
);
