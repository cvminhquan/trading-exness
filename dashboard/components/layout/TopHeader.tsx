"use client";

import { BotStatusIndicator, ConnectionIndicator } from "@/components/shared/BotStatusIndicator";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/shared/Skeletons";
import { UI } from "@/lib/i18n/vi";
import { useSessionContext } from "@/queries/use-trading-queries";

export const TopHeader = () => {
  const { data, isLoading } = useSessionContext();

  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
      <div className="flex flex-col gap-3 px-4 py-3 md:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-base font-semibold tracking-tight text-slate-100">{UI.appName}</p>
          <p className="text-xs text-slate-500">{UI.appSubtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isLoading ? (
            <>
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-7 w-24" />
              <Skeleton className="h-7 w-28" />
            </>
          ) : data ? (
            <>
              <Badge variant="default" className="normal-case">
                {data.tradingMode}
              </Badge>
              <BotStatusIndicator status={data.botStatus} />
              <ConnectionIndicator status={data.connectionStatus} />
              <span className="hidden text-xs text-slate-500 sm:inline">{data.accountLabel}</span>
            </>
          ) : null}
          <Badge variant="info" className="normal-case">
            {UI.mockData}
          </Badge>
        </div>
      </div>
    </header>
  );
};
