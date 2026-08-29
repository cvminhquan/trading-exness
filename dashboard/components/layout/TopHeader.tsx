"use client";

import { AccountSwitcher } from "@/components/layout/AccountSwitcher";
import { BotStatusIndicator, ConnectionIndicator } from "@/components/shared/BotStatusIndicator";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/shared/Skeletons";
import { isApiDataSource } from "@/lib/config/env";
import { ACCOUNT_SWITCH, UI } from "@/lib/i18n/vi";
import { useSessionContext } from "@/queries/use-trading-queries";

export const TopHeader = () => {
  const { data, isLoading } = useSessionContext();

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
              <span className="hidden text-xs text-slate-500 sm:inline">{data.accountLabel}</span>
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
