"use client";

import { AccountSwitcher } from "@/components/layout/AccountSwitcher";
import {
  BotStatusIndicator,
  ConnectionIndicator,
  FreshnessIndicator,
} from "@/components/shared/BotStatusIndicator";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/shared/Skeletons";
import { isApiDataSource } from "@/lib/config/env";
import { A11Y, ACCOUNT_SWITCH, BOT_STATUS_LABELS, CANDLE_ENGINE, PAPER_TRADING, SIGNAL_ENGINE, UI } from "@/lib/i18n/vi";
import { aggregateQuoteFreshness } from "@/lib/market/freshness";
import { useQuotes, useSessionContext } from "@/queries/use-trading-queries";

export const TopHeader = () => {
  const { data, isLoading } = useSessionContext();
  const quotesQuery = useQuotes();
  const quoteFreshness = quotesQuery.data ? aggregateQuoteFreshness(quotesQuery.data) : null;

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="flex flex-col gap-3 px-4 py-3 md:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-base font-semibold tracking-tight text-slate-900">{UI.appName}</p>
          <p className="text-xs text-slate-500">{UI.appSubtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <AccountSwitcher variant="compact" />
          {isLoading ? (
            <>
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-7 w-24" />
              <Skeleton className="h-7 w-28" />
            </>
          ) : data ? (
            <>
              <Badge
                variant={data.accountProfile === "live" ? "warning" : "info"}
                className="normal-case"
              >
                {data.accountProfile === "live" ? ACCOUNT_SWITCH.liveFull : ACCOUNT_SWITCH.demoFull}
              </Badge>
              <Badge variant="default" className="normal-case">
                {data.tradingMode}
              </Badge>
              <BotStatusIndicator status={data.botStatus} />
              <ConnectionIndicator status={data.connectionStatus} />
              {data.connectionStatus === "CONNECTED" && quoteFreshness ? (
                <FreshnessIndicator freshness={quoteFreshness} />
              ) : null}
              <span className="hidden text-xs text-slate-500 sm:inline">{data.accountLabel}</span>
              {data.candleEngine ? (
                <span
                  className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600"
                  aria-label={A11Y.liveCandleEngine}
                >
                  <span className="text-slate-500">{CANDLE_ENGINE.label}:</span>
                  <BotStatusIndicator status={data.candleEngine.status} compact />
                  <span className="sr-only">{BOT_STATUS_LABELS[data.candleEngine.status]}</span>
                  <span>
                    {CANDLE_ENGINE.lastClosed}:{" "}
                    {data.candleEngine.lastClosedAt ?? CANDLE_ENGINE.none}
                  </span>
                  <span>
                    {CANDLE_ENGINE.dataSource}: {data.candleEngine.dataSource}
                  </span>
                </span>
              ) : null}
              {data.signalEngine ? (
                <span
                  className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600"
                  aria-label={A11Y.researchSignalEngine}
                >
                  <span className="text-slate-500">{SIGNAL_ENGINE.label}:</span>
                  <BotStatusIndicator status={data.signalEngine.status} compact />
                  <span className="sr-only">{BOT_STATUS_LABELS[data.signalEngine.status]}</span>
                  <span>
                    {SIGNAL_ENGINE.strategy}: {data.signalEngine.strategy}
                  </span>
                  <span>
                    {SIGNAL_ENGINE.lastSignal}: {data.signalEngine.lastSignal ?? SIGNAL_ENGINE.none}
                  </span>
                </span>
              ) : null}
              {data.paperExecution ? (
                <span
                  className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600"
                  aria-label={A11Y.paperTrading}
                >
                  <Badge variant="warning" className="normal-case">
                    {PAPER_TRADING.mode}
                  </Badge>
                  <BotStatusIndicator status={data.paperExecution.status} compact />
                  <span className="sr-only">{BOT_STATUS_LABELS[data.paperExecution.status]}</span>
                  <span>
                    {PAPER_TRADING.lastExecution}:{" "}
                    {data.paperExecution.lastExecution ?? PAPER_TRADING.none}
                  </span>
                </span>
              ) : null}
            </>
          ) : null}
          <Badge variant={isApiDataSource() ? "success" : "info"} className="normal-case">
            {isApiDataSource() ? UI.liveData : UI.mockData}
          </Badge>
        </div>
      </div>
    </header>
  );
};
